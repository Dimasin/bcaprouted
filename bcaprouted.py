#!/usr/bin/python3 -u
# For working with modem, user must have permissions to read/write to modem port (modemport in config.env)
# sudo chmod 666 /dev/ttyUSB2 или sudo usermod -a -G dialout $USER после чего нужно перелогиниться в систему
# Разрешаем сервису управлять только одним конкретным VPN-соединением
# Выполните sudo visudo и добавьте в самый конец файла (замените myuser на ваше имя пользователя)
# bcru ALL=(ALL) NOPASSWD: /usr/bin/systemctl start openvpn-client@master.service, /usr/bin/systemctl stop openvpn-client@master.service, /usr/bin/systemctl is-active openvpn-client@master.service

import numbers
import os
import sys
import serial
from time import sleep, time
import subprocess
import requests
import re
from dotenv import load_dotenv
import ipaddress
import signal
from threading import Event

# Взаимодействие с systemd, статус завершения, сигналы
EXIT_RUNTIME_SUCCESS = 0
EXIT_RUNTIME_ERROR = 1
EXIT_CONFIG_ERROR = 10

# Событие для остановки основного цикла 
# не нужно указывать дополнительное ожидание для юнита TimeoutStopSec=300
stop_event = Event()

def handle_stop_signal(signum, frame):
  """
  Обработчик сигналов для корректного завершения скрипта
  """
  print(f"Get signal {signum} normal exit...")
  stop_event.set()

# Регистрируем обработчик сигналов
signal.signal(signal.SIGTERM, handle_stop_signal)
signal.signal(signal.SIGINT, handle_stop_signal)

# загрузка конфига
load_dotenv('config.env')

interface = os.getenv("interface")
ipaddrs = os.getenv("ipaddrs")
modemport = os.getenv("modemport")
cycles_dead = int(os.getenv("cycles_dead","5"))
cycles_live = int(os.getenv("cycles_live","5"))
ntfy_url = os.getenv("ntfy_url","")
ntfy_lp = os.getenv("ntfy_login_pass","")
vpn_unit = os.getenv("vpn_unit","")


def is_valid(ip):
  """
  Валидация ip
  """
  try:
    return str(ipaddress.ip_address(ip.strip()))
  except ValueError:
    return None


# Оставляем только те ip, что прошли проверку
iphosts = [res for ip in ipaddrs.split(',') if (res := is_valid(ip))]
  
# Проверяем, что все необходимые переменные окружения заданы
required = ["interface", "modemport"]
missing = [k for k in required if not os.getenv(k)]

# Если не все обязательные переменные заданы, выводим ошибку и говорим 
# systemd больше не перезапускать сервис
if (missing) or (iphosts is not None and not iphosts):
  print(f"Missing config variables: {', '.join(missing)}")
  sys.exit(EXIT_CONFIG_ERROR)


def ping(host: str):
  """
  Делает пинг по ip адресу, но выводит только ошибки, при ошибке возврат отличен от нуля
  """
  pr = subprocess.run(['/usr/bin/ping', host, '-c 1', '-n', '-I', interface], shell=False, stdout=subprocess.PIPE, encoding='utf-8')
  if(pr.returncode != 0):
    print(pr.stdout.replace('\n\n','\n')[:-1])
  return pr.returncode


def modem_control(actions: str):
  """
  Универсальная функция управления модемом:
    "connect"  -> AT^NDISDUP=1,1,"internet"
    "disconnect" -> AT^NDISDUP=1,0,"internet"
    "signal" -> AT+CSQ
  """
  commands = {
    "connect": b'AT^NDISDUP=1,1,"internet"\r\n',
    "disconnect": b'AT^NDISDUP=1,0,"internet"\r\n',
    "signal": b'AT^HCSQ?\r\n' #b'AT^CERSSI?\r\n'#b'AT^CSNR?\r\n'#b'AT^HCSQ?\r\n' #b'AT+CSQ\r\n'
  }
  if actions not in commands:
    raise ValueError("Unknown action. Use: connect | disconnect | signal")
  try:
    with serial.Serial(modemport, 115200, timeout=5, write_timeout=5) as ser:
      # Очищаем буфер перед запросом
      ser.reset_input_buffer()
      # Отправляем команду
      ser.write(commands[actions])
      sleep(1)
      # Читаем ответ
      response = repr(ser.read_all().decode('utf-8', errors='ignore'))
      match = re.search(r'OK', response)
      if not match:
        print(f"Unexpected modem response: {response.strip()}")
        return
      if actions == "signal":
        # print(f"Мodem response: {response.strip()}")
        # Ищем число в строке вида "+CSQ: 18,99"
        # match = re.search(r'\+CSQ:\s*(\d+),', response)
        match = re.search(r'\^HCSQ:"LTE",(\d+),(\d+),(\d+),(\d+)', response)
        if match:
          numbers = [int(n) for n in match.groups()]
          if (numbers and len(numbers) == 4):
            rssi = numbers[0] - 121
            rsrp = numbers[1] - 141
            sinr = int(numbers[2] * 0.2) - 20
            rsrq = int(numbers[3] * 0.5) - 20
            print(f"Мodem response: RSSI {rssi} dBm, RSRP {rsrp} dBm, RSRQ {rsrq} dB, SINR {sinr} dB")
          # rssi = int(match.group(1))
          # Переводим в dBm (упрощенная формула: dBm = 2 * rssi - 113)
          # dbm = 2 * rssi - 113 if rssi != 99 else "N/A"
          # print(f"Мodem response: RSSI {rssi}, Signal {dbm} dBm")
      else:
        print(f"Мodem response: {response.strip()} wait 10s ...")
        stop_event.wait(10)  # Если переключали интернет ждем 10 сек, чтобы успело все сработать
  except Exception as e:
    print(f"Modem error: {e}")
  return


def send_ntfy_message(message: str):
  """
  Отправляет уведомление в ntfy
  """
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


def resend_ntfy_message(message: str):
  """
  Пытается отправить уведомление в ntfy несколько раз с паузой, если не удается, выводит ошибку
  """
  for _ in range(12):  # Пытаемся отправить сообщение 12 раз с интервалом в 5 секунд (1 минута)
    if send_ntfy_message(message):
      return True
    stop_event.wait(5)
  print("Failed to send alert after multiple attempts.")
  return False


def vpn_control(action: str):
  """
  Управление VPN через systemd, если указано vpn_unit в конфиге 
  и у пользователя есть права на управление этим юнитом
  """
  allowed_actions = {"start", "stop", "is-active"}
  if action not in allowed_actions:
    raise ValueError(f"Unsupported action: {action}")

  if not vpn_unit or not vpn_unit.strip():
    print("Service name is empty")
    return
  # Выполняем команду от sudo (смотри комментарий в начале)
  cmd = ["sudo", "systemctl", action, vpn_unit]
  result = subprocess.run(cmd, capture_output=True, text=True)
  # Выводим все что systemctl вернул
  print(f"vpn_control({action}) return {result}")
  return


###############################################################################################
#Приводим openvpn и модем в состояние OFF
vpn_control("stop")
modem_control("disconnect")
modem_on = False
cycle_dead = cycle_live = 0

while not stop_event.is_set():
  start_time = time()
  modem_control("signal")
  inet_down = True
  for iphost in iphosts:
    if (ping(iphost)==0):
      inet_down = False
      msg = f'Host {iphost} is OK'
      cycle_dead = 0
      cycle_live += 1                  #Если хотя бы один хост откликнулся, считаем сеть жива
      if (cycle_live > cycles_live):
        cycle_dead = 0
        cycle_live = 1
        if (modem_on):                 #Если модем включен, отключаем
          modem_on = False
          vpn_control("stop")          #Отключаем VPN
          modem_control("disconnect")
          resend_ntfy_message('Modem DOWN!!!')  #Шлем уведомление
          msg = 'Internet UP!!!'
      break

  if (inet_down):
    msg = 'All hosts are not ping! '         #Если хосты не пингуются плюсуем dead, обнуляем live
    cycle_dead += 1
    cycle_live = 0
    if (cycle_dead > cycles_dead):   #Если прошло > cycles_dead циклов - обнуляем счетчики
      cycle_dead = 1
      cycle_live = 0
      if (not modem_on):             #Если модем выключен, включаем
        modem_on = True
        modem_control("connect")
        vpn_control("start")         #Поднимаем VPN
        resend_ntfy_message('Modem UP!!!')  #Шлем уведомление
        msg = 'Internet DOWN!!!'

  #пишем в консоль что произошло и пауза
  print(f'{msg:<32} | Cycles not ping = {cycle_dead:<4} | Cycles OK = {cycle_live:<4} |')
  stop_event.wait(max(0, 60 - (time() - start_time))) # Чтобы цикл примерно соответствовал 1 минуте

sys.exit(EXIT_RUNTIME_SUCCESS)