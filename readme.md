1. Готовим каталоги сервиса.

sudo sudo mkdir -p /opt/bcaprouted
sudo chown -R $USER:$USER /opt/bcaprouted

Копируем файлы: bcaprouted.py, config.env.example, requirements.txt

cd /opt/bcaprouted
cp config.env.example config.env

Правим config.env под свой комп

Дальше:

python3 -m venv venv
source venv/bin/activate

После этого в консоли появится префикс:

(venv) user@server:$

which python

Должно быть:
/opt/bcaprouted/venv/bin/python

Дальше:

pip install -r requirements.txt


2. Копируем bcaprouted.service в /etc/systemd/system

Меняем в /etc/systemd/system/bcaprouted.service имя пользователя в опции User= на свое,
которое использовали в команде sudo chown -R $USER:$USER /opt/bcaprouted

Дальше:

sudo chown root:root /etc/systemd/system/bcaprouted.service
sudo systemctl daemon-reload
sudo systemctl start bcaprouted

Проверяем, если все в порядке:

sudo systemctl enable bcaprouted

Если нет:

sudo systemctl stop bcaprouted

Смотрим логи, ищем ошибки, исправляем:

journalctl -r



