#!/bin/bash

# Проверяем, существует ли файл resolv.conf
if [ ! -f "/etc/resolv.conf" ]; then
    echo "Файл /etc/resolv.conf не найден"
    exit 1
fi

# Проверяем права на запись
if [ ! -w "/etc/resolv.conf" ]; then
    echo "Нет прав на запись в файл /etc/resolv.conf"
    exit 1
fi

# Проверяем наличие строки с 8.8.8.8
if grep -q "8.8.8.8" "/etc/resolv.conf"; then
    echo "DNS сервер 8.8.8.8 уже настроен"
else
    # Добавляем новые строки в конец файла
    echo "nameserver 8.8.8.8" >> /etc/resolv.conf
    echo "nameserver 8.8.4.4" >> /etc/resolv.conf
    echo "DNS серверы 8.8.8.8 и 8.8.4.4 успешно добавлены"

    sudo systemctl daemon-reload
    sudo systemctl restart docker
fi
