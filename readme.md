# Проект микросервиса Bcaprouted для Linux.
Сделан для управления LTE модемом Huawei E3372 в режиме Gateway+NDIS (CDC_NCM) при отключении / включении основного интернет соединения. Дополнительно может управлять уже настроенным OpenVPN клиентским соединением с внешним узлом и сообщать в [ntfy](https://ntfy.sh) о включении / выключении модема. Как настроить модем в такой композиции отдельная тема и лучше искать информацию об этом на 4pda.

Для контроля основного интернет соединения делается `ping` на несколько внешних надежных узлов. Например, ближайший узел маршрутизации провайдера и другие пингуемые внешние стабильные серверы. Рекомендуется задать как минимум два внешних IP адреса, три внешних IP хватит выше крыши.

По сути сервис лишь управляет включением и отключением модема, основная работа выполняется компонентами OC: получение DHCP, настройка DNS и маршрутизации. Поэтому, перед тем как браться настраивать этот сервис нужно убедится в правильной работе сетевых компонетов ОС при ручном переключении с основного канала на модем и обратно.

## 1. Готовим систему.
Для запуска сервиса желательно создать системного пользователя, например, `bcru` и группу `bcru`.
```bash
sudo useradd -r -U -m -d /opt/bcaprouted -s /usr/sbin/nologin bcru
```
Даем пользователю нужные права на управление модемом.
```bash
sudo usermod -aG dialout bcru
```
Для управления OpenVPN клиентом нужно добавить разрешения в `/etc/sudoers`:
```bash
sudo visudo 
```
В самый конец файла добавляем строку:
```txt
bcru ALL=(ALL) NOPASSWD: /usr/bin/systemctl start openvpn-client@master.service, /usr/bin/systemctl stop openvpn-client@master.service, /usr/bin/systemctl is-active openvpn-client@master.service
```
Если включать/отключать OpenVPN не нужно, тогда опцию `vpn_unit` из конфига `config.env` можно удалить или оставить пустой, соответственно и в `/etc/sudoers` добавлять ничего не нужно.

## 2. Готовим каталоги сервиса.

Если каталог уже создан командой выше, то создание каталога можно пропустить.
```bash
sudo sudo mkdir -p /opt/bcaprouted
```
Качаем и копируем файлы `bcaprouted.py`, `config.env.example`, `requirements.txt` в каталог `/opt/bcaprouted`
```bash
sudo cp bcaprouted.py /opt/bcaprouted
```
```bash
sudo cp config.env.example /opt/bcaprouted
```
```bash
sudo cp requirements.txt /opt/bcaprouted
```
Создаем свой конфиг файл на основе шаблона:
```bash
sudo cp /opt/bcaprouted/config.env.example /opt/bcaprouted/config.env
```
Правим `config.env` под свой комп. 
Обязательно нужно заполнить валидными данными все опции конфига, кроме уже упомянутой `vpn_unit`.

Далее делаем (вместо `bcru` подставляем своего пользователя):
```bash
sudo chown -R bcru:bcru /opt/bcaprouted
```
```bash
sudo chmod 600 /opt/bcaprouted/config.env
```
Становимся пользователем `bcru`:
```bash
sudo -u bcru -s /bin/bash
```
Дальше команды выполняем уже от пользователя `bcru`:
```bash
cd /opt/bcaprouted
```
```bash
python3 -m venv venv
```
```bash
source venv/bin/activate
```
После этого в консоли появится префикс:
```txt
(venv) bcru@server:$
```
Выполняем:
```bash
which python
```
Должно быть:
```txt
/opt/bcaprouted/venv/bin/python
```
Дальше выполняем:
```bash
pip install -r requirements.txt
```
Проверяем установку пакетов командой:
```bash
pip list
```
Затем выходим из учетки `bcru`:
```bash
exit
```

## 3. Настройка сервиса

Качаем `bcaprouted.service` и меняем в нем имя пользователя в опции `User=bcru` на свое, которое создали в пункте 1. Копируем в каталог `systemd`:
```bash
sudo cp bcaprouted.service /etc/systemd/system
```
Дальше выполняем:
```bash
sudo chown root:root /etc/systemd/system/bcaprouted.service
```
```bash
sudo systemctl daemon-reload
```
```bash
sudo systemctl start bcaprouted
```
Проверяем по логам отклик модема и пинга, если все в порядке выполняем:
```bash
sudo systemctl enable bcaprouted
```
Если не все в порядке или совсем ничего не работает делаем:
```bash
sudo systemctl stop bcaprouted
```
Смотрим логи `journalctl -r`, ищем ошибки, исправляем ...
