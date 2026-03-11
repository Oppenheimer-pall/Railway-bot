"""
UzRailways.uz saytidan poyezd va joy ma'lumotlarini oluvchi modul.
"""

import asyncio
import logging
import aiohttp
from datetime import datetime
from bs4 import BeautifulSoup
import re

logger = logging.getLogger(__name__)

# Stantsiya kodlari (uzrailways.uz standart nomlari)
STATION_CODES = {
    "Toshkent":    "2900000",
    "Samarqand":   "2900100",
    "Buxoro":      "2900200",
    "Qarshi":      "2900400",
    "Termiz":      "2900500",
    "Namangan":    "2900600",
    "Andijon":     "2900700",
    "Farg'ona":    "2900750",
    "Navoiy":      "2900800",
    "Jizzax":      "2900900",
    "Guliston":    "2901000",
    "Urganch":     "2901100",
    "Nukus":       "2901200",
    "Denov":       "2901300",
    "Xiva":        "2901400",
}

WAGON_TYPE_MAP = {
    "platskart": "1",
    "kupe":      "2",
    "sv":        "3",
    "orindiq":   "4",
    "any":       None,
}

class UzRailwaysScraper:
    """
    uzrailways.uz (chipta.uzrailways.uz) saytidan poyezd ma'lumotlarini oladi.
    
    Umumiy scraping oqimi:
    1. POST /search → poyezdlar ro'yxatini oladi
    2. Har bir poyezd uchun GET /train/{id}/wagons → vagonlar va joylarni tekshiradi
    """
    
    BASE_URL  = "https://chipta.uzrailways.uz"
    SEARCH_EP = "/ru/api/trains"
    
    HEADERS = {
        "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept":          "application/json, text/html,*/*",
        "Accept-Language": "ru-RU,ru;q=0.9,uz;q=0.8",
        "Referer":         "https://chipta.uzrailways.uz/",
        "Content-Type":    "application/json",
    }

    def __init__(self):
        self.session = None

    async def _get_session(self):
        if self.session is None or self.session.closed:
            timeout = aiohttp.ClientTimeout(total=30)
            self.session = aiohttp.ClientSession(headers=self.HEADERS, timeout=timeout)
        return self.session

    def _resolve_station(self, name: str) -> str:
        """Shahar nomini stantsiya kodiga aylantiradi."""
        for key, code in STATION_CODES.items():
            if key.lower() == name.lower():
                return code
        return name  # Agar topilmasa, to'g'ridan-to'g'ri nom bilan qidiriladi

    async def check_seats(self, from_city: str, to_city: str, travel_date: str, wagon_type: str = "any") -> dict:
        """
        Berilgan yo'nalish va sanada bo'sh joy mavjudligini tekshiradi.
        
        Returns:
            {
                "available": bool,
                "trains": [{"number", "departure", "arrival", "seats", "price"}, ...]
            }
        """
        session = await self._get_session()
        
        # Sanani formatlash: "25.03.2025" → "2025-03-25"
        try:
            date_obj = datetime.strptime(travel_date, "%d.%m.%Y")
            api_date = date_obj.strftime("%Y-%m-%d")
        except ValueError:
            api_date = travel_date

        from_code = self._resolve_station(from_city)
        to_code   = self._resolve_station(to_city)

        # ── 1-qadam: Poyezdlarni qidirish ───────────────────────────────────
        search_payload = {
            "fromSCode": from_code,
            "toSCode":   to_code,
            "dateFrom":  api_date,
            "counts":    {"adults": 1, "children": 0},
        }

        try:
            async with session.post(
                f"{self.BASE_URL}{self.SEARCH_EP}", json=search_payload
            ) as resp:
                if resp.status != 200:
                    logger.warning(f"Search API {resp.status}: {from_city}→{to_city}")
                    return {"available": False, "trains": [], "error": f"HTTP {resp.status}"}
                
                data = await resp.json(content_type=None)
        except aiohttp.ClientError as e:
            logger.error(f"Network error: {e}")
            return {"available": False, "trains": [], "error": str(e)}
        
        # ── 2-qadam: Natijalarni tahlil qilish ──────────────────────────────
        trains_raw = data.get("trains") or data.get("data") or data.get("result") or []
        
        if not trains_raw:
            return {"available": False, "trains": []}

        available_trains = []
        wtype_filter = WAGON_TYPE_MAP.get(wagon_type)

        for train in trains_raw:
            seats_info = await self._get_train_seats(session, train, wtype_filter)
            if seats_info and seats_info.get("total_seats", 0) > 0:
                available_trains.append({
                    "number":    train.get("number") or train.get("trainNumber") or "?",
                    "departure": train.get("departureTime") or train.get("timeFrom") or "?",
                    "arrival":   train.get("arrivalTime") or train.get("timeTo") or "?",
                    "seats":     seats_info["total_seats"],
                    "price":     seats_info.get("min_price", "noma'lum"),
                    "wagons":    seats_info.get("wagons", []),
                })
            await asyncio.sleep(0.5)  # Serverga yuklanish bermaslik

        return {
            "available": len(available_trains) > 0,
            "trains":    available_trains,
        }

    async def _get_train_seats(self, session, train: dict, wtype_filter=None) -> dict:
        """
        Bitta poyezdning vagonlari va bo'sh joylarini tekshiradi.
        """
        train_id = (
            train.get("id") or train.get("trainId") or
            train.get("sessionId") or train.get("number")
        )
        if not train_id:
            # Agar train_id bo'lmasa, train ichidagi joylarni to'g'ridan tekshir
            return self._parse_inline_seats(train, wtype_filter)

        try:
            async with session.get(
                f"{self.BASE_URL}/ru/api/trains/{train_id}/wagons"
            ) as resp:
                if resp.status != 200:
                    return self._parse_inline_seats(train, wtype_filter)
                wagons_data = await resp.json(content_type=None)
        except Exception as e:
            logger.debug(f"Wagon API error: {e}")
            return self._parse_inline_seats(train, wtype_filter)

        wagons = wagons_data.get("wagons") or wagons_data.get("data") or wagons_data or []
        if not isinstance(wagons, list):
            return self._parse_inline_seats(train, wtype_filter)

        total_seats = 0
        min_price   = float("inf")
        valid_wagons = []

        for wagon in wagons:
            wtype = str(wagon.get("type") or wagon.get("classType") or "")
            free  = int(wagon.get("freeSeats") or wagon.get("availableSeats") or wagon.get("seats") or 0)
            price = wagon.get("price") or wagon.get("minPrice") or 0

            if wtype_filter and wtype != wtype_filter:
                continue
            if free > 0:
                total_seats += free
                if price and float(str(price).replace(",", "")) < min_price:
                    min_price = float(str(price).replace(",", ""))
                valid_wagons.append({"type": wtype, "seats": free, "price": price})

        return {
            "total_seats": total_seats,
            "min_price":   f"{min_price:,.0f} so'm" if min_price < float("inf") else "noma'lum",
            "wagons":      valid_wagons,
        }

    @staticmethod
    def _parse_inline_seats(train: dict, wtype_filter=None) -> dict:
        """
        Agar alohida API bo'lmasa, train ob'ektining o'zidan joylarni oladi.
        """
        seats = (
            train.get("freeSeats") or train.get("availableSeats") or
            train.get("totalFreeSeats") or 0
        )
        price = train.get("price") or train.get("minPrice") or "noma'lum"
        return {
            "total_seats": int(seats),
            "min_price":   f"{price} so'm" if isinstance(price, (int, float)) else price,
            "wagons":      [],
        }

    async def close(self):
        if self.session and not self.session.closed:
            await self.session.close()
