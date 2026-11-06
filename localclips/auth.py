"""Official SIWC public-client OAuth, PKCE + verified OIDC, loopback callback."""
import base64
import hashlib
import hmac
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import secrets
import time
from urllib.parse import urlencode, urlsplit, parse_qs
from urllib.request import Request, build_opener, ProxyHandler, HTTPRedirectHandler
from urllib.error import HTTPError
import jwt
from . import credentials

AUTH='https://auth.openai.com'
RESOURCE='https://api.openai.com/v1'
TOKEN=AUTH+'/api/accounts/oauth/token'
PLAN='chatgpt.tokens.use.direct'


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):
        raise RuntimeError('Redirect HTTP non consentito per credenziali o trascrizioni.')


def request(url,payload=None,headers=None,form=False,stream=False):
    data=None
    headers=dict(headers or {})
    if payload is not None:
        data=(urlencode(payload) if form else json.dumps(payload)).encode()
        headers['Content-Type']='application/x-www-form-urlencoded' if form else 'application/json'
    try:
        response=build_opener(ProxyHandler({}),NoRedirect()).open(Request(url,data,headers),timeout=120)
    except HTTPError as exc:
        # Never include response body/URL: they can carry credentials or transcript.
        raise RuntimeError(f'Servizio AI: HTTP {exc.code}. Controlla accesso, modello e limiti del piano.') from None
    if stream:
        return response
    with response:
        raw=response.read(8_000_000)
        return json.loads(raw) if raw else {}


def metadata():
    value=request(AUTH+'/.well-known/openid-configuration')
    if value.get('issuer')!=AUTH:
        raise ValueError('Issuer OpenID inatteso.')
    for key in ('jwks_uri','revocation_endpoint'):
        parsed=urlsplit(value[key])
        if parsed.scheme!='https' or parsed.hostname!='auth.openai.com':
            raise ValueError('Endpoint OpenID inatteso.')
    return value


def validate_identity(token,client_id,nonce,discovery=None):
    discovery=discovery or metadata()
    keys=request(discovery['jwks_uri'])
    header=jwt.get_unverified_header(token)
    if header.get('alg')!='RS256':
        raise ValueError('Algoritmo ID token non consentito.')
    key=next((k for k in keys['keys'] if k.get('kid')==header.get('kid')),None)
    if key is None:
        raise ValueError('Firma ID token non riconosciuta.')
    claims=jwt.decode(token,jwt.PyJWK.from_dict(key).key,algorithms=['RS256'],audience=client_id,
                      issuer=AUTH,options={'require':['exp','iat','sub','aud','iss','nonce']})
    if not hmac.compare_digest(str(claims['nonce']),nonce):
        raise ValueError('Nonce OAuth non valido.')
    return claims


def public_status():
    store=credentials.read()
    return {'active':store.get('active',''),'accounts':[
        {'id':key,'label':f"{v.get('email','Account')} · {key[-8:]}",
         'connected':bool(v.get('access_token')),'plan':PLAN in v.get('scopes',[])}
        for key,v in store['accounts'].items()]}


def sign_in(account_id,allow_plan,open_url,timeout=300):
    store=credentials.read()
    credentials.write(store)  # persist stable host before the first attempt
    old=store['accounts'].get(account_id,{})
    client=old.get('client_id','dynamic_agent_client')
    state,nonce,verifier=[secrets.token_urlsafe(40) for _ in range(3)]
    result={}
    class Callback(BaseHTTPRequestHandler):
        def log_message(self,*args):
            pass
        def do_GET(self):
            parsed=urlsplit(self.path)
            query=parse_qs(parsed.query)
            if parsed.path!='/auth/callback' or not hmac.compare_digest(query.get('state',[''])[0],state):
                self.send_error(400,'Invalid authorization state'); return
            result.update({k:v[0] for k,v in query.items()})
            self.send_response(200)
            self.send_header('Content-Type','text/plain; charset=utf-8')
            self.end_headers()
            self.wfile.write('Puoi tornare a LocalClips AI. Verifica accesso in corso.'.encode())
    with HTTPServer(('127.0.0.1',0),Callback) as server:
        server.timeout=.5
        redirect=f'http://127.0.0.1:{server.server_port}/auth/callback'
        query={'client_id':client,'ext_agent_host_id':store['host_id'],'response_type':'code',
               'redirect_uri':redirect,'scope':'openid profile email'+(' offline_access resource.invoke '+PLAN if allow_plan else ''),
               'resource':RESOURCE,'state':state,'nonce':nonce,'code_challenge_method':'S256',
               'code_challenge':base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')}
        if client=='dynamic_agent_client':
            query['agent_name_hint']='LocalClips AI'
        elif old.get('id_token'):
            query['id_token_hint']=old['id_token']
        open_url(AUTH+'/api/accounts/authorize?'+urlencode(query))
        deadline=time.monotonic()+timeout
        while not result and time.monotonic()<deadline:
            server.handle_request()
    if not result:
        raise RuntimeError('Accesso scaduto dopo 5 minuti. Riprova.')
    if result.get('error'):
        raise RuntimeError('Accesso non autorizzato. Nessuna credenziale salvata.')
    issued=result.get('client_id',client)
    if not issued or issued=='dynamic_agent_client' or (client!='dynamic_agent_client' and issued!=client):
        raise ValueError('Registrazione OAuth incompleta o account diverso.')
    token=request(TOKEN,{'grant_type':'authorization_code','client_id':issued,'code':result['code'],
                        'code_verifier':verifier,'redirect_uri':redirect,'resource':RESOURCE},form=True)
    claims=validate_identity(token['id_token'],issued,nonce)
    if old and claims['sub']!=old['subject']:
        raise ValueError('L’identità non corrisponde all’account selezionato.')
    record={'client_id':issued,'subject':claims['sub'],'email':claims.get('email','Account'),
            'scopes':token.get('scope','').split(),'expires_at':time.time()+token.get('expires_in',0)}
    record.update({k:token[k] for k in ('access_token','id_token','refresh_token') if k in token})
    store['accounts'][issued]=record
    store['active']=issued
    credentials.write(store)
    return public_status()


def access_token(account_id):
    # GUI serializes jobs; the lock also excludes refresh from another instance.
    import msvcrt
    lock=credentials.credential_path().with_suffix('.lock')
    with lock.open('a+b') as stream:
        stream.seek(0)
        if stream.read(1)==b'':
            stream.write(b'0'); stream.flush()
        stream.seek(0)
        msvcrt.locking(stream.fileno(),msvcrt.LK_LOCK,1)
        try:
            store=credentials.read()
            record=store['accounts'].get(account_id,{})
            if PLAN not in record.get('scopes',[]):
                raise RuntimeError('Autorizza separatamente l’uso del piano ChatGPT nelle Impostazioni.')
            if not record.get('access_token'):
                raise RuntimeError('Accedi nuovamente con ChatGPT.')
            if record.get('expires_at',0)<time.time()+90:
                if not record.get('refresh_token'):
                    raise RuntimeError('Sessione scaduta. Accedi nuovamente con ChatGPT.')
                token=request(TOKEN,{'grant_type':'refresh_token','client_id':record['client_id'],
                                    'refresh_token':record['refresh_token'],'resource':RESOURCE},form=True)
                for k in ('access_token','refresh_token'):
                    if k in token: record[k]=token[k]
                if 'scope' in token: record['scopes']=token['scope'].split()
                record['expires_at']=time.time()+token.get('expires_in',0)
                credentials.write(store)
            if PLAN not in record['scopes']:
                raise RuntimeError('Permesso di uso del piano ChatGPT revocato.')
            return record['access_token']
        finally:
            stream.seek(0)
            msvcrt.locking(stream.fileno(),msvcrt.LK_UNLCK,1)


def sign_out(account_id):
    store=credentials.read()
    record=store['accounts'].get(account_id,{})
    warning=''
    if record.get('refresh_token'):
        try:
            request(metadata()['revocation_endpoint'],{'token':record['refresh_token'],
                    'token_type_hint':'refresh_token','client_id':record['client_id']},form=True)
        except Exception:
            warning='Revoca remota non confermata. Puoi disconnettere l’app dalle impostazioni ChatGPT.'
    for k in ('access_token','refresh_token','id_token','scopes','expires_at'):
        record.pop(k,None)
    credentials.write(store)
    return public_status()|{'warning':warning}
