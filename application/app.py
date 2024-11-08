from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Dict
from datetime import datetime, time, timedelta
import sqlite3

app = FastAPI()

# Modell för bokningsförfrågan
class BookingRequest(BaseModel):
    room_id: int
    tid: str  # Tid i formatet "HH:MM"
    datum: str  # Datum i formatet "YYYY-MM-DD"

# Funktion för att ansluta till databasen
def get_db_connection():
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    return conn

# Validera tidens format och om den är inom öppettider
def validate_time_format(tid: str) -> bool:
    try:
        tid_obj = datetime.strptime(tid, "%H:%M").time()
        return time(8, 0) <= tid_obj <= time(17, 0)
    except ValueError:
        return False

# POST-endpoint för att boka ett rum
@app.post("/book-room")
async def book_room(data: BookingRequest):
    room_id = data.room_id
    tid = data.tid
    datum = data.datum
    
    # Validera tidens format och intervall
    if not validate_time_format(tid):
        raise HTTPException(status_code=422, detail="Ogiltigt tidsformat. Ange tiden i formatet HH:MM mellan 08:00 och 17:00.")

    # Kontrollera datumformat och konvertera till datumobjekt
    try:
        booking_date = datetime.strptime(datum, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=422, detail="Ogiltigt datumformat. Ange datumet i formatet YYYY-MM-DD.")
    
    # Kontrollera att datumet inte ligger i det förflutna
    today = datetime.today().date()
    if booking_date < today:
        raise HTTPException(status_code=422, detail="Datumet ligger i det förflutna. Välj ett framtida datum.")
    
    # Kontrollera att datumet är en vardag (måndag-fredag)
    if booking_date.weekday() > 4:
        raise HTTPException(status_code=422, detail="Endast bokningar mellan måndag och fredag är tillåtna.")

    if booking_date > today + timedelta(days=5):
        raise HTTPException(status_code=422, detail="Datumet ligger för långt i framtiden. Välj ett datum denna vecka.")
    # Förbered rums-ID
    room = f"Room {room_id}"

    # Anslut till databasen och kontrollera om tiden är ledig
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT available FROM bookings WHERE room = ? AND date = ? AND time = ?", (room, datum, tid))
    result = cursor.fetchone()

    # Om tiden är ledig, boka rummet
    if result and result["available"] == 1:
        cursor.execute("UPDATE bookings SET available = 0 WHERE room = ? AND date = ? AND time = ?", (room, datum, tid))
        conn.commit()
        conn.close()
        return {"message": f"Rummet {room} är nu bokat för {tid} den {datum}."}
    else:
        conn.close()
        raise HTTPException(status_code=409, detail=f"Rummet {room} är redan bokat för {tid} den {datum}. Välj en annan tid.")

#GET-endpoint för att visa alla lediga rum och tider för de kommande fem vardagarna
@app.get("/available-rooms-week", response_model=Dict[str, Dict[str, List[str]]])
async def available_rooms_week():
    weekdays = []
    today = datetime.today()
    while len(weekdays) < 5: #Genom loopen hämta vardagar mån-fre med weekday metoden 5an där motsvarar att vi vill ha 0-4
        if today.weekday() < 5:
            weekdays.append(today.date().isoformat())
        today += timedelta(days=1) #De sparas dag för dag.

    conn = get_db_connection() #Skapar anslutning till databasen
    cursor = conn.cursor()
    result = {}

    #För varje dag i weekdays gör vi en SQL-fråga till databasen för att hämta alla rum som är tillgängliga och deras bokningsbara tider.
    for day in weekdays:   
        cursor.execute("SELECT room, time FROM bookings WHERE date = ? AND available = 1", (day,))
        rows = cursor.fetchall() #Dessa sparas i rows
        daily_availability = {}
        
        #För varje rad i rows läggs rummet och dess tid i en ordbok som vi kallat daily_availability som organiserar vilka tider
        #som är lediga för varje rum den dagen.
        for row in rows: 
            room = row["room"]
            tid = row["time"]
            if room not in daily_availability:
                daily_availability[room] = []
            daily_availability[room].append(tid)
        
        #När daily_availability fyllts med datan från databasen så sparar vi det i result med dagens datum som nyckel
        result[day] = daily_availability
    
    conn.close()

    if result:
        return result
    else:
        raise HTTPException(status_code=404, detail="Inga lediga rum finns för de kommande fem vardagarna.")
