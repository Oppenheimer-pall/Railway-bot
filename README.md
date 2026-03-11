# 🚂 UzRailways Joy Monitor Bot

Poyezdlarda bo'sh joy paydo bo'lganda darhol Telegram orqali xabar beruvchi bot.

---

## 🚀 O'rnatish va ishga tushirish

### 1. Telegram botini yarating
1. Telegramda [@BotFather](https://t.me/BotFather) ga yozing
2. `/newbot` buyrug'ini yuboring
3. Bot nomini va username kiriting
4. Olingan **TOKEN** ni `config.py` ga joylashtiring:
   ```python
   BOT_TOKEN = "1234567890:ABCdef..."
   ```

### 2. Python va kutubxonalarni o'rnating
```bash
# Python 3.10+ kerak
pip install -r requirements.txt
```

### 3. Botni ishga tushiring
```bash
python bot.py
```

---

## 📦 Fayl tuzilmasi
```
uzrailways_bot/
├── bot.py          — Asosiy bot (handlerlar, FSM, fon tekshiruvi)
├── scraper.py      — uzrailways.uz saytidan ma'lumot oluvchi modul
├── config.py       — Sozlamalar (token, interval, DB yo'li)
├── requirements.txt
└── README.md
```

---

## ⚙️ Sozlamalar (`config.py`)

| Parametr | Izoh | Standart |
|---|---|---|
| `BOT_TOKEN` | BotFather tokeni | — |
| `DB_PATH` | SQLite fayli | `monitors.db` |
| `CHECK_INTERVAL` | Tekshirish intervali (soniya) | `300` (5 daqiqa) |
| `MAX_MONITORS_PER_USER` | Bir foydalanuvchiga max kuzatuvlar | `5` |

---

## 🤖 Bot buyruqlari

| Buyruq | Izoh |
|---|---|
| `/start` | Botni ishga tushirish |
| `/mymonitors` | Kuzatuvlarni ko'rish |
| `/cancel` | Joriy jarayonni bekor qilish |

---

## 🔄 Qanday ishlaydi?

```
Foydalanuvchi → Yo'nalish + Sana + Vagon turi kiritadi
      ↓
Bot ma'lumotni SQLite ga saqlaydi
      ↓
Fon task har 5 daqiqada chipta.uzrailways.uz ga so'rov yuboradi
      ↓
Bo'sh joy topilsa → Telegram xabari + "Bilet sotib olish" tugmasi
      ↓
Kuzatuv avtomatik o'chiriladi (takroriy xabar kelmaydi)
```

---

## 🏙️ Qo'llab-quvvatlanadigan stantsiyalar

Toshkent, Samarqand, Buxoro, Qarshi, Termiz, Namangan, Andijon, 
Farg'ona, Navoiy, Jizzax, Guliston, Urganch, Nukus, Denov, Xiva

Yangi stantsiya qo'shish uchun `scraper.py` dagi `STATION_CODES` lug'atini to'ldiring.

---

## 📊 Ma'lumotlar bazasi (SQLite)

**monitors** jadvali:
- `id` — kuzatuv ID
- `user_id` / `chat_id` — Telegram foydalanuvchi
- `from_city` / `to_city` — yo'nalish
- `travel_date` — sana
- `wagon_type` — vagon turi
- `active` — 1 = faol, 0 = to'xtatilgan
- `notified` — 1 = xabar yuborildi

---

## ⚠️ Eslatmalar

- Bot uzrailways.uz saytining rasmiy API si o'zgarsa, `scraper.py` ni yangilash kerak bo'lishi mumkin.
- Saytning shartlari va robots.txt ga rioya qiling.
- Tekshirish intervalini juda qisqa qilmang (minimal 2-3 daqiqa).
