1. Готовим систему.
Создаем системного пользователя "bcru" и группу "bcru" для запуска сервиса. Даем пользователю нужные права.

sudo useradd -r -U -m -d /opt/bcaprouted -s /usr/sbin/nologin bcru
sudo usermod -aG dialout bcru
sudo visudo 

Для управления OpenVPN клиентом в самый конец добавляем:

bcru ALL=(ALL) NOPASSWD: /usr/bin/systemctl start openvpn-client@master.service, /usr/bin/systemctl stop openvpn-client@master.service, /usr/bin/systemctl is-active openvpn-client@master.service

Если включать/отключать OpenVPN не нужно, тогда опцию "vpn_unit" из конфига "config.env" можно удалить или оставить пустой.

2. Готовим каталоги сервиса.

Если каталог уже создан командой выше, то создание каталога можно пропустить.

sudo sudo mkdir -p /opt/bcaprouted

Копируем файлы: bcaprouted.py, config.env.example, requirements.txt

sudo cp bcaprouted.py /opt/bcaprouted
sudo cp config.env.example /opt/bcaprouted
sudo cp requirements.txt /opt/bcaprouted

Создаем конфиг файл:

sudo cp /opt/bcaprouted/config.env.example /opt/bcaprouted/config.env

Правим config.env под свой комп. 
Обязательно нужно заполнить валидными данными все опции конфига, кроме уже упомянутой "vpn_unit".

Далее:

sudo chown -R bcru:bcru /opt/bcaprouted
sudo chmod 600 /opt/bcaprouted/config.env

Становимся пользователем bcru

sudo -u bcru -s /bin/bash

Дальше команды выполняем уже от пользователя "bcru"

cd /opt/bcaprouted
python3 -m venv venv
source venv/bin/activate

После этого в консоли появится префикс:

(venv) bcru@server:$

Выполняем:

which python

Должно быть:
/opt/bcaprouted/venv/bin/python

Дальше:

pip install -r requirements.txt

Проверяем установку пакетов:

pip list

Затем выходим из учетки bcru:

exit

3. Настройка сервиса

Меняем в bcaprouted.service имя пользователя в опции User=bcru на свое,
которое создали в пункте 1.

sudo cp bcaprouted.service /etc/systemd/system

Дальше:

sudo chown root:root /etc/systemd/system/bcaprouted.service
sudo systemctl daemon-reload
sudo systemctl start bcaprouted

Проверяем по логам отклик модема и пинга, если все в порядке выполняем:

sudo systemctl enable bcaprouted

Если нет:

sudo systemctl stop bcaprouted

Смотрим логи, ищем ошибки, исправляем:

journalctl -r