import argparse
import sys

import requests
from bs4 import BeautifulSoup


LOGIN_URL = "https://portal.vspu.ru/login"


def login(email: str, password: str) -> bool:
    session = requests.Session()

    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/140.0 Safari/537.36"
        )
    })

    try:
        # Получаем страницу входа
        page = session.get(LOGIN_URL, timeout=20)
        page.raise_for_status()

        soup = BeautifulSoup(page.text, "html.parser")

        # Данные формы
        data = {
            "LoginForm[username]": email,
            "LoginForm[password]": password,
            "RememberMe": "1",
        }

        # Если портал использует CSRF — автоматически добавляем его
        csrf = soup.find("input", {"name": "_csrf"})

        if csrf and csrf.get("value"):
            data["_csrf"] = csrf["value"]

        # Отправляем форму
        response = session.post(
            LOGIN_URL,
            data=data,
            timeout=20,
            allow_redirects=True,
        )

        print(f"POST status: {response.status_code}")
        print(f"Final URL: {response.url}")
        print(f"Redirects: {len(response.history)}")

        # Если форма логина осталась — вероятно, вход не прошёл
        result_soup = BeautifulSoup(response.text, "html.parser")
        login_form = result_soup.select_one("#login-form")

        if response.ok and not login_form:
            print("✅ ВХОД ПОХОЖЕ УСПЕШНЫЙ")
            return True

        print("❌ ВХОД НЕ ВЫПОЛНЕН")
        print("Проверь email и пароль.")
        return False

    except requests.RequestException as exc:
        print(f"❌ HTTP ошибка: {type(exc).__name__}: {exc}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Тест входа на portal.vspu.ru"
    )

    parser.add_argument("email", help="E-mail")
    parser.add_argument("password", help="Пароль")

    args = parser.parse_args()

    success = login(args.email, args.password)

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
