from aiohttp import web
from time import time
import config
from utils import validate_address, validate_cookie, validate_recaptcha
from db import check_ip, check_claims, update_claimtime
from ravencoin.core import b2lx, COIN
from ravencoin.rpc import RavenProxy
   
async def index(request):
   return web.FileResponse('./www/faucet.html')
   
async def claim(request):
   # handle faucet claim
   data = await request.post()
   cookie = request.cookies.get(config.cookie_name,'')
   if config.debug:
      print(request.remote,data,cookie)
   claim_address = data['_address']
   recaptcha = data.get('_recaptcha','')
   
   # anti-DoS / sanity check
   if len(claim_address) > config.maxAddressLen:
      print(f"Invalid request from IP {request.remote}: Address field too long (DoS?)",flush = True)
      return web.json_response({'status': 'Error','msg':'Address is invalid'})
   if len(recaptcha) > 1024: # should be enough?!
      print(f"Invalid request from IP {request.remote}: Recaptcha field too long (DoS?)",flush = True)
      return web.json_response({'status': 'Error','msg':'Recaptcha error'})
   
   # check address is correct format
   if not validate_address(claim_address):
      print(f"Invalid request from IP {request.remote}: Address invalid",flush = True)
      return web.json_response({'status': 'Error','msg':f'Address {claim_address} is invalid'})
      
   # limit claims by address
   if not check_claims("address",claim_address):
      print(f"Too many claims for address {claim_address} from IP {request.remote}",flush = True)
      return web.json_response({'status': 'Error','msg':'Maximum claims exceeded. Please try again later'})
      
   # validate cookie
   if not validate_cookie(cookie):
      print(f"Invalid cookie from IP {request.remote}",flush = True)
      return web.json_response({'status': 'Error','msg':'Cookie validation error. Javascript and cookies must be enabled for this faucet to work'})
      
   # limit claims by cookie
   if not check_claims("cookie",cookie):
      print(f"Too many claims for cookie from IP {request.remote}",flush = True)
      return web.json_response({'status': 'Error','msg':'Maximum claims exceeded. Please try again later'})

   # limit claims by ip
   if not check_ip(request.remote):
      print(f"Too many claims from IP {request.remote}",flush = True)
      return web.json_response({'status': 'Error','msg':'Maximum claims exceeded. Please try again later'})
   
   # validate reCAPTCHA   
   if not validate_recaptcha(recaptcha):
      print(f"Recaptcha validation failed for IP {request.remote}",flush = True)
      return web.json_response({'status': 'Error','msg':'reCAPTCHA validation failed'})
      
   try:
       rvn = RavenProxy(service_url=config.coin_daemon_url,datadir=config.args.datadir)
       txid = b2lx(rvn.sendtoaddress(claim_address,config.claim_amount))
       update_claimtime(request.remote,claim_address,cookie)
       print(f"Sent {config.claim_amount} {config.denom} to address {claim_address} for IP {request.remote}",flush = True)
       return web.json_response({'status': 'Success','msg':f'Sent {config.claim_amount/COIN} {config.denom} to {claim_address},<br> \
       txid <a href="https://testnet.ravencoin.network/tx/{txid}">{txid}</s>'})
   except Exception as e:
       if config.debug:
          print(e)
       print(f"Error sending {config.claim_amount/COIN} {config.denom} to address {claim_address} for IP {request.remote}",flush = True)
       return web.json_response({'status': 'Error','msg':'Error sending coins. Please try again later'})

status_cache = {} # cache used to reduce calls to daemon
status_cache_lifetime = 30 # seconds
              
async def status(request):
   cache_time = status_cache.get('time',0)

   if int(time()) <= cache_time+status_cache_lifetime: # use cached result
      balance = status_cache.get('balance',0)
      blocks = status_cache.get('blocks',0)
      status = status_cache.get('status',"")
   else:
      try:
         rvn = RavenProxy(service_url=config.coin_daemon_url,datadir=config.args.datadir)
         balance = rvn.getbalance()
         blocks = rvn.getblockcount()
         status = 'OK'
      except Exception as e:
         if config.debug:
            print(e)
         balance = 0
         blocks = 0
         status = 'ERROR'

      status_cache['status'] = status
      status_cache['balance'] = balance
      status_cache['blocks'] = blocks
      status_cache['time'] = int(time())

   return web.json_response({'status': status,'balance': balance / COIN, 'blocks': blocks})
   
async def info(request):
   return web.json_response({'faucet_address': config.faucet_address})
   