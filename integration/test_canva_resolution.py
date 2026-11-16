import urllib.request
urls=["https://media.canva.com/v2/image-resize/format:PNG/height:200/quality:100/uri:ifs%3A%2F%2FM%2Ffa2f7d1a-1fd5-4573-8a77-15473534114c/watermark:F/width:151?csig=AAAAAAAAAAAAAAAAAAAAAFizWTMeq1zmUSGARNAJb7PvkfiSVVwRLY3zzXAaNl_V&exp=1794886536&osig=AAAAAAAAAAAAAAAAAAAAAHbppL14WAwHhTjiGVpP011PBSlRikmr8YRwkcDSIc3-&signer=media-rpc&token=AAIAAU0AJGZhMmY3ZDFhLTFmZDUtNDU3My04YTc3LTE1NDczNTM0MTE0YwAAAAABoeeTC0AS3pjocSSuuTSgwHBWfuiiLeeEq5xM7cUxOkRILWFO1A&x-canva-quality=thumbnail","https://media.canva.com/v2/image-resize/format:PNG/height:1440/quality:100/uri:ifs%3A%2F%2FM%2Ffa2f7d1a-1fd5-4573-8a77-15473534114c/watermark:F/width:1092?csig=AAAAAAAAAAAAAAAAAAAAAFizWTMeq1zmUSGARNAJb7PvkfiSVVwRLY3zzXAaNl_V&exp=1794886536&osig=AAAAAAAAAAAAAAAAAAAAAHbppL14WAwHhTjiGVpP011PBSlRikmr8YRwkcDSIc3-&signer=media-rpc&token=AAIAAU0AJGZhMmY3ZDFhLTFmZDUtNDU3My04YTc3LTE1NDczNTM0MTE0YwAAAAABoeeTC0AS3pjocSSuuTSgwHBWfuiiLeeEq5xM7cUxOkRILWFO1A&x-canva-quality=original"]
for i,url in enumerate(urls):
 try:
  with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0'}),timeout=15) as resp:
   data=resp.read()
   from PIL import Image
   from io import BytesIO
   im=Image.open(BytesIO(data))
   print(i,resp.status,im.size,len(data))
 except Exception as e: print(i,str(e))
