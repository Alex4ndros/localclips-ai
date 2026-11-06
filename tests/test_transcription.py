from types import SimpleNamespace

from localclips.transcription import transcribe


def test_cuda_exception_retries_cpu_and_keeps_word_timing(tmp_path,monkeypatch):
    import faster_whisper
    import ctranslate2
    (tmp_path/'model.bin').write_bytes(b'test-double')
    calls=[]
    class FakeWhisper:
        def __init__(self,path,device,**kw):
            calls.append((device,kw['local_files_only']))
            if device=='cuda':
                raise RuntimeError('CUDA out of memory')
        def transcribe(self,*args,**kw):
            assert kw['word_timestamps'] and kw['vad_filter']
            word=SimpleNamespace(start=.2,end=.8,word='Privacy.')
            segment=SimpleNamespace(start=.2,end=.8,text='Privacy.',words=[word])
            return iter([segment]),SimpleNamespace(language='it',duration=1.)
    monkeypatch.setattr(faster_whisper,'WhisperModel',FakeWhisper)
    monkeypatch.setattr(ctranslate2,'get_cuda_device_count',lambda:1)
    captions,language,device,warning=transcribe('unused.wav',str(tmp_path),'auto')
    assert calls==[('cuda',True),('cpu',True)]
    assert device=='cpu' and language=='it' and 'out of memory' in warning
    assert captions[0].words[0].start==.2
    assert captions[0].words[0].end==.8
