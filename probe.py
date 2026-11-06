import requests
from bs4 import BeautifulSoup

SOURCES = {
    "Milyoner": "https://m.milyoner549.com/tr/sports/live/event-view/Soccer",
    "Nolurki": "https://nolurki.com/spor",
    "Scandal": "https://scandal.bet/spor"
}

headers = {
    "User-Agent": "Mozilla/5.0 (Linux; Android 10) AppleWebKit/537.36 Chrome/120.0 Mobile Safari/537.36"
}

for name, url in SOURCES.items():
    print("\n" + "=" * 35)
    print(name)

    try:
        response = requests.get(
            url,
            headers=headers,
            timeout=25
        )

        soup = BeautifulSoup(response.text, "html.parser")

        print("HTTP:", response.status_code)
        print("Sayfa başlığı:", soup.title.get_text(strip=True) if soup.title else "Bulunamadı")
        print("HTML boyutu:", len(response.text))
        print("Maç kelimesi var mı:", "Virtual" in response.text)
        print("İçerik tipi:", response.headers.get("Content-Type"))

    except Exception as error:
        print("Bağlantı hatası:", str(error))
