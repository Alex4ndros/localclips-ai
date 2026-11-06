import io
import json
import time
import threading
from urllib.parse import urlsplit,parse_qs,urlencode
from http.client import HTTPConnection
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from localclips import auth, credentials
from localclips.semantic import chunks, decisions, local_endpoint, completed_text
from localclips.domain import Caption


def test_dpapi_roundtrip_and_no_plaintext(tmp_path,monkeypatch):
    path=tmp_path/'protected.bin'
    monkeypatch.setattr(credentials,'credential_path',lambda:path)
    original={'host_id':'test','accounts':{'key':'secret-123'},'active':''}
    credentials.write(original)
    assert b'secret-123' not in path.read_bytes()
    assert credentials.read()==original


def signed_token(monkeypatch,nonce='expected',aud='oaiapp_test',expiry=None):
    private=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    key=json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(private.public_key()))
    key['kid']='test'
    monkeypatch.setattr(auth,'request',lambda *_args,**_kwargs:{'keys':[key]})
    return jwt.encode({'iss':auth.AUTH,'sub':'user','aud':aud,'iat':int(time.time()),
                       'exp':expiry or int(time.time())+120,'nonce':nonce},private,algorithm='RS256',headers={'kid':'test'})


def test_oidc_signature_audience_nonce_expiry(monkeypatch):
    discovery={'jwks_uri':'unused'}
    token=signed_token(monkeypatch)
    assert auth.validate_identity(token,'oaiapp_test','expected',discovery)['sub']=='user'
    with pytest.raises(ValueError): auth.validate_identity(token,'oaiapp_test','wrong',discovery)
    with pytest.raises(jwt.InvalidAudienceError): auth.validate_identity(token,'other','expected',discovery)
    expired=signed_token(monkeypatch,expiry=int(time.time())-60)
    with pytest.raises(jwt.ExpiredSignatureError): auth.validate_identity(expired,'oaiapp_test','expected',discovery)


def test_oauth_callback_pkce_and_separate_plan_consent(tmp_path,monkeypatch):
    monkeypatch.setattr(credentials,'credential_path',lambda:tmp_path/'oauth.dpapi')
    seen={}
    def open_browser(url):
        query={k:v[0] for k,v in parse_qs(urlsplit(url).query).items()}
        seen.update(query)
        assert query['client_id']=='dynamic_agent_client'
        assert query['code_challenge_method']=='S256'
        assert auth.PLAN not in query['scope']
        callback=query['redirect_uri']+'?'+urlencode({'state':query['state'],'code':'test','client_id':'oaiapp_test'})
        def send():
            parsed=urlsplit(callback)
            connection=HTTPConnection(parsed.hostname,parsed.port,timeout=5)
            connection.request('GET',parsed.path+'?'+parsed.query)
            assert connection.getresponse().status==200
            connection.close()
        threading.Thread(target=send,daemon=True).start()
    def exchange(url,payload,**kwargs):
        assert payload['client_id']=='oaiapp_test' and payload['redirect_uri']==seen['redirect_uri']
        assert len(payload['code_verifier'])>=43
        return {'id_token':'test','access_token':'secret','expires_in':3600,'scope':'openid profile email'}
    monkeypatch.setattr(auth,'request',exchange)
    monkeypatch.setattr(auth,'validate_identity',lambda *a:{'sub':'user','email':'test@example.invalid'})
    result=auth.sign_in('',False,open_browser,timeout=8)
    assert result['active']=='oaiapp_test'
    assert result['accounts'][0]['connected'] and not result['accounts'][0]['plan']
    assert 'secret' not in json.dumps(result)


def test_no_external_lmstudio_or_redirect_credentials():
    assert local_endpoint('http://127.0.0.1:1234')=='http://127.0.0.1:1234/v1'
    for url in ('https://example.com/v1','http://192.168.1.1/v1','http://localhost@evil.com','http://127.0.0.1/v1?x=1'):
        with pytest.raises(ValueError): local_endpoint(url)
    with pytest.raises(RuntimeError): auth.NoRedirect().redirect_request(None,None,None,None,None,None)


def test_chunks_keep_absolute_timestamps_and_budget():
    captions=[Caption(i*3,i*3+2,'Un modello locale tutela i dati e la privacy.') for i in range(500)]
    blocks=list(chunks(captions,4096))
    assert len(blocks)>10 and blocks[-1][-1]['end']==1499
    assert all(len(json.dumps(b,ensure_ascii=False).encode())<2400 for b in blocks)
    assert all(b[0]['start']<a[-1]['end'] for a,b in zip(blocks,blocks[1:]))


def test_model_decisions_reject_hallucinated_times_and_nan():
    captions=[Caption(0,4,'Perché usare un LLM locale?'),Caption(4.2,20,'Per proteggere la privacy dei dati.')]
    row={'start':0,'end':20,'score':80,'title':'LLM privati','reason':'Domanda e risposta','layout':'face'}
    assert len(decisions(json.dumps({'clips':[row]}),captions,100,10,30))==1
    for bad in ({'start':90,'end':100},{'score':float('nan')},{'title':5}):
        assert not decisions(json.dumps({'clips':[row|bad]}),captions,100,10,30)


def test_stream_requires_completion_and_handles_quota():
    def stream(events):
        return io.BytesIO(b''.join(b'data: '+json.dumps(e).encode()+b'\n\n' for e in events))
    delta={'type':'response.output_text.delta','delta':'hello'}
    assert completed_text(stream([delta,{'type':'response.completed'}]))=='hello'
    with pytest.raises(RuntimeError): completed_text(stream([delta]))
    with pytest.raises(RuntimeError,match='subscription_sharing_usage_limit_exceeded'):
        completed_text(stream([delta,{'type':'response.failed','response':{'error':{'code':'subscription_sharing_usage_limit_exceeded'}}}]))
