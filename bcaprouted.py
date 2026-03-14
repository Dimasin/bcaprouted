#!/usr/bin/python3 -u
# For debug:
# sudo chmod 666 /dev/ttyUSB2 или sudo usermod -a -G dialout $USER

import os
import sys
import serial
from time import sleep, time
import subprocess, signal
import telebot
import requests
import re
from dotenv import load_dotenv
import ipaddress

# Статус завершения, взаимодействующий с systemd
EXIT_RUNTIME_ERROR = 1
EXIT_CONFIG_ERROR = 10

# загрузка конфига
load_dotenv('config.env')

interface = os.getenv("interface")
ipaddrs = os.getenv("ipaddrs")
modemport = os.getenv("modemport")
cycles_dead = int(os.getenv("cycles_dead","5"))
cycles_live = int(os.getenv("cycles_live","5"))
TOKEN = os.getenv("Telegram_token","")
chat_id = os.getenv("Telrgram_chat_id","")
ntfy_url = os.getenv("ntfy_url","")
ntfy_lp = os.getenv("ntfy_login_pass","")

# Валидация ip
def is_valid(ip):
  try:
    return str(ipaddress.ip_address(ip.strip()))
  except ValueError:
    return None

# Оставляем только те ip, что прошли проверку
iphosts = [res for ip in ipaddrs.split(',') if (res := is_valid(ip))]

required = ["interface", "modemport"]
missing = [k for k in required if not os.getenv(k)]

if (missing) or (iphosts is not None and not iphosts):
  print(f"Missing config variables: {', '.join(missing)}")
  sys.exit(EXIT_CONFIG_ERROR)

pause = 60
cycle_dead = 0
cycle_live = 0
msg = ''
modem_on = False

#Делает пинг по ip адресу, при ошибке возврат отличен от нуля
def pingip(ip):
  response = os.system('/usr/bin/ping -n -c 1 -I ' + interface + ' ' + ip)
  return response

#Делает пинг по ip адресу, но выводит только ошибки, при ошибке возврат отличен от нуля
def ping(host):
  pr = subprocess.run(['/usr/bin/ping', host, '-c 1', '-n', '-I', interface], shell=False, stdout=subprocess.PIPE, encoding='utf-8')
  if(pr.returncode != 0):
    print(pr.stdout.replace('\n\n','\n')[:-1])
  return pr.returncode

#Подключает/отключает модем
def modem_operate(op):
  sleep(5)
  try:
    with serial.Serial(modemport, 115200, timeout=5, write_timeout=5) as ser:
      if (op):
        ser.write(b'AT^NDISDUP=1,1,"internet"\r')
      else:
        ser.write(b'AT^NDISDUP=1,0,"internet"\r')
      sleep(1)
  except Exception as e:
    print(f"Modem error: {e}")
    raise
  return

#Получает уровень сигнала модема
def get_signal_level():
  try:
    with serial.Serial(modemport, 115200, timeout=5, write_timeout=5) as ser:
      # Очищаем буфер перед запросом
      ser.reset_input_buffer()
      # Отправляем команду
      ser.write(b'AT+CSQ\r\n')
      sleep(1)
      # Читаем ответ
      response = ser.read_all().decode('utf-8', errors='ignore')
      # Ищем число в строке вида "+CSQ: 18,99"
    match = re.search(r'\+CSQ:\s*(\d+),', response)
    if match:
      rssi = int(match.group(1))
      # Переводим в dBm (упрощенная формула: dBm = 2 * rssi - 113)
      dbm = 2 * rssi - 113 if rssi != 99 else "N/A"
      print(f"RSSI: {rssi} | Signal: {dbm} dBm")
  except Exception as e:
    print(f"Modem error: {e}")
  return

#Переподключает openvpn клиент
def vpn_operate(updown):
  p = subprocess.Popen(['pgrep', '-a', 'openvpn'], stdout=subprocess.PIPE)
  out, err = p.communicate()
  for line in out.splitlines():
    line = bytes.decode(line)
    if ('master.ovpn' not in line):
      continue
    pid = int(line.split(None, 1)[0])
    os.kill(pid, signal.SIGKILL)
  sleep(5)
  if (updown):
    os.system('/usr/sbin/openvpn --config /etc/openvpn/client/master.ovpn --daemon')
    sleep(5)

#Отправляет уведомление в телеграмм
def sendtlg(msg): 
  tb = telebot.TeleBot(TOKEN)
  try:
    tb.send_message(chat_id, msg)
  except:
    print('Error send tlgrm message: ' + msg)
    return False
  return True

#Отправляет уведомление в ntfy
def send_ntfy_message(message):
  try:
    response = requests.post(
      ntfy_url,
      data=message.encode('utf-8'),
      headers={
        "Authorization": f"{ntfy_lp}",
        "Title": "Bcaprouted Alert",  # Заголовок уведомления
        "Priority": "max", # Можно менять на min, low, high, max
      }
    )
    if response.status_code == 200:
      print("Alert success!")
      return True
    else:
      print(f"Sending alert error: {response.status_code}")
      return False
  except Exception as e:
    print(f"Unknow alert error: {e}")
    return False

def resend_ntfy_message(message):
  print(message)
  for _ in range(12):  # Пытаемся отправить сообщение 12 раз с интервалом в 5 секунд (1 минута)
    if send_ntfy_message(message):
      return True
    sleep(5)
  print("Failed to send alert after multiple attempts.")
  return False

#Приводим модем и openvpn в состояние OFF
try:
  modem_operate(False)
except:
  print("Failed to initialize modem state. Exiting.")
  sys.exit(EXIT_RUNTIME_ERROR)

#vpn_operate(False)

while True:
  start_time = time()
  get_signal_level()
  live_or_dead = False
  for iphost in iphosts:
    if (ping(iphost)==0):
      msg = f'Host {iphost} is OK'
      live_or_dead = True               #Если хотя бы один хост откликнулся, считаем сеть жива
      break
    else:
      msg = f'All hosts dead!'

  if (live_or_dead):
    cycle_dead = 0
    cycle_live += 1
  else:                                 #Если хосты не пингуются плюсуем dead, обнуляем live
    cycle_dead += 1
    cycle_live = 0

  if (cycle_dead > cycles_dead):     #Если прошло cycles_dead циклов - обнуляем счетчики
    msg = 'Route dead!'
    cycle_dead = 0
    cycle_live = 0
    if (not modem_on):     #Если модем выключен, включаем
      modem_on = True
      modem_operate(modem_on)
      #vpn_operate(True)       #Поднимаем VPN
      resend_ntfy_message('Modem UP!!!')  #Шлем уведомление

  if (cycle_live > cycles_live):       #Если пинги есть cycles_live циклов, обнуляем счетчики
    msg = 'Route live!'
    cycle_live = 0
    cycle_dead = 0
    if (modem_on):           #Если модем включен, отключаем
      modem_on = False
      modem_operate(modem_on)
      #vpn_operate(False)        #Отключаем VPN
      resend_ntfy_message('Modem DOWN!!!')  #Шлем уведомление

  #пишем в консоль что произошло и пауза
  print(msg  + ' | cycle_dead = ' + str(cycle_dead) + ' | cycle_live = ' + str(cycle_live))
  sleep(max(0, pause - (time() - start_time)))