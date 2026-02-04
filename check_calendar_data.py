#!/usr/bin/env python
"""
Script para verificar stays y reservations del tenant demo
"""

import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = f"postgresql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"

try:
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    
    print("=== Stays para tenant 17 ===")
    cursor.execute('''
        SELECT id, estado, reservation_id, checkin_real, checkout_real
        FROM stays
        WHERE empresa_usuario_id = 17
        ORDER BY id
        LIMIT 10
    ''')
    stays = cursor.fetchall()
    print(f"Total: {len(stays)}")
    for row in stays:
        print(f"  Stay {row[0]}: estado={row[1]}, reservation_id={row[2]}, checkin={row[3]}, checkout={row[4]}")
    
    print("\n=== Reservations para tenant 17 ===")
    cursor.execute('''
        SELECT id, estado, fecha_checkin, fecha_checkout, nombre_temporal
        FROM reservations
        WHERE empresa_usuario_id = 17
        ORDER BY id
        LIMIT 10
    ''')
    reservations = cursor.fetchall()
    print(f"Total: {len(reservations)}")
    for row in reservations:
        print(f"  Reservation {row[0]}: estado={row[1]}, checkin={row[2]}, checkout={row[3]}, nombre={row[4]}")
    
    print("\n=== ReservationRooms para tenant 17 ===")
    cursor.execute('''
        SELECT rr.id, rr.reservation_id, rr.room_id, r.numero
        FROM reservation_rooms rr
        JOIN reservations res ON rr.reservation_id = res.id
        JOIN rooms r ON rr.room_id = r.id
        WHERE res.empresa_usuario_id = 17
        LIMIT 10
    ''')
    res_rooms = cursor.fetchall()
    print(f"Total: {len(res_rooms)}")
    for row in res_rooms:
        print(f"  ResRoom {row[0]}: reservation_id={row[1]}, room_id={row[2]}, room_numero={row[3]}")
    
    cursor.close()
    conn.close()
except Exception as e:
    print(f'✗ Error: {e}')
