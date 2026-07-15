#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Скрипт для получения ИНН через сервис ФНС
Корректно форматирует серию и номер паспорта
"""

import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

import requests
import time
import logging
import re
import os
from typing import Optional

LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(message)s"
DATE_FORMAT = "%H:%M:%S"

LOG_TO_CONSOLE = True
LOG_TO_FILE = True

ANSI_PATTERN = re.compile(r"\x1b\[[0-9;]*m")


class Colors:
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    BLUE = "\033[94m"
    RESET = "\033[0m"
    BOLD = "\033[1m"


class StripAnsiFormatter(logging.Formatter):
    def format(self, record):
        record.msg = ANSI_PATTERN.sub("", record.getMessage())
        return super().format(record)


_handlers = []
if LOG_TO_CONSOLE:
    _console = logging.StreamHandler()
    _console.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT))
    _handlers.append(_console)
if LOG_TO_FILE:
    _log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "log")
    os.makedirs(_log_dir, exist_ok=True)
    _log_path = os.path.join(_log_dir, "inn_checker.log")
    _file = logging.FileHandler(_log_path, encoding="utf-8")
    _file.setFormatter(StripAnsiFormatter(LOG_FORMAT, datefmt=DATE_FORMAT))
    _handlers.append(_file)

logging.basicConfig(
    level=logging.INFO,
    handlers=_handlers
)
logger = logging.getLogger(__name__)

class NalogInnClient:
    """Клиент для получения ИНН через сервис ФНС"""

    MAIN_PAGE = "https://service.nalog.ru/inn.do"
    CONSENT_URL = "https://service.nalog.ru/static/personal-data-proc.json"
    PROC_URL = "https://service.nalog.ru/inn-new-proc.json"

    HEADERS = {
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
        "Connection": "keep-alive",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Origin": "https://service.nalog.ru",
        "X-Requested-With": "XMLHttpRequest",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    }

    POLL_STEP = 1000
    POLL_MAX = 60000
    REQUEST_TIMEOUT_MS = 180000

    def __init__(self, timeout: int = 30, retries: int = 3, retry_delay: float = 2.0):
        self.timeout = timeout
        self.retries = retries
        self.retry_delay = retry_delay
        self.session = requests.Session()
        self.session.headers.update(self.HEADERS)
        self._consent_given = False

    def _give_consent(self) -> bool:
        """Подтверждает согласие на обработку персональных данных"""
        try:
            logger.info(f"{Colors.BLUE}→ Загрузка страницы сервиса...{Colors.RESET}")
            response = self.session.get(self.MAIN_PAGE, timeout=self.timeout, allow_redirects=True)
            response.raise_for_status()

            consent_data = {"personalData": "1", "svc": "inn", "from": "/inn.do"}
            xhr_headers = {
                "Referer": response.url,
            }
            r = self.session.post(
                self.CONSENT_URL,
                data=consent_data,
                headers=xhr_headers,
                timeout=self.timeout
            )
            r.raise_for_status()
            content_type = r.headers.get("content-type", "")
            if "application/json" in content_type:
                logger.info(f"{Colors.GREEN}✓ Согласие подтверждено{Colors.RESET}")
                self._consent_given = True
                return True
            else:
                logger.warning(f"{Colors.YELLOW}⚠️ Неожиданный ответ при согласии: {content_type}{Colors.RESET}")
                return False
        except Exception as e:
            logger.error(f"{Colors.RED}✗ Ошибка при подтверждении согласия: {e}{Colors.RESET}")
            return False

    def _init_session(self) -> bool:
        """Инициализация сессии: загрузка страницы и подтверждение согласия"""
        if self._consent_given:
            return True
        if not self._give_consent():
            return False
        response = self.session.get(self.MAIN_PAGE, timeout=self.timeout)
        response.raise_for_status()
        if "frmInn" in response.text:
            logger.info(f"{Colors.GREEN}✓ Форма ИНН доступна{Colors.RESET}")
            return True
        logger.warning(f"{Colors.YELLOW}⚠️ Форма ИНН не найдена на странице{Colors.RESET}")
        return False

    def _prepare_docno(self, series: str, number: str) -> str:
        """Форматирует серию и номер паспорта в формат XX XX XXXXXX"""
        series_clean = ''.join(filter(str.isdigit, str(series)))
        number_clean = ''.join(filter(str.isdigit, str(number)))

        if len(series_clean) < 4:
            raise ValueError("Серия паспорта должна содержать 4 цифры")
        if len(number_clean) < 6:
            raise ValueError("Номер паспорта должен содержать 6 цифр")

        return f"{series_clean[:2]} {series_clean[2:4]} {number_clean[:6]}"

    def get_inn(
        self,
        last_name: str,
        first_name: str,
        patronymic: str,
        birth_date: str,
        passport_series: str,
        passport_number: str,
        passport_issue_date: str
    ) -> Optional[str]:
        """
        Запрашивает ИНН по данным физического лица.

        :return: ИНН или None
        """
        if not self._init_session():
            return None

        form_data = {
            "c": "find",
            "doctype": "21",
            "captcha": "",
            "captchaToken": "",
            "fam": last_name.strip(),
            "nam": first_name.strip(),
            "otch": patronymic.strip() if patronymic else "",
            "bdate": birth_date,
            "docno": self._prepare_docno(passport_series, passport_number),
            "docdt": passport_issue_date
        }

        logger.info(f"{Colors.BLUE}Запрос ИНН: {last_name} {first_name} {patronymic} | "
                     f"Дата рождения: {birth_date} | Паспорт: {passport_series}******{Colors.RESET}")

        for attempt in range(self.retries):
            try:
                r = self.session.post(
                    self.PROC_URL,
                    data=form_data,
                    timeout=self.timeout
                )

                if r.status_code != 200:
                    logger.error(f"{Colors.RED}HTTP {r.status_code}: {r.text[:200]}{Colors.RESET}")
                    return None

                result = r.json()

                if "ERRORS" in result:
                    err_msg = next(iter(result["ERRORS"].values()), ["Неизвестная ошибка"])[0]
                    logger.error(f"{Colors.RED}Ошибка: {err_msg[:100]}{Colors.RESET}")
                    return None

                if result.get("captchaRequired"):
                    logger.warning(f"{Colors.YELLOW}Требуется CAPTCHA — автоматический запрос невозможен{Colors.RESET}")
                    return None

                request_id = result.get("requestId")
                if not request_id:
                    logger.error(f"{Colors.RED}Нет requestId в ответе{Colors.RESET}")
                    return None

                return self._poll_result(request_id)

            except requests.exceptions.RequestException as e:
                logger.error(f"{Colors.RED}Ошибка запроса (попытка {attempt+1}/{self.retries}): {e}{Colors.RESET}")

            if attempt < self.retries - 1:
                delay = self.retry_delay * (attempt + 1)
                logger.info(f"{Colors.BLUE}Повтор через {delay}с...{Colors.RESET}")
                time.sleep(delay)

        return None

    def _poll_result(self, request_id: str) -> Optional[str]:
        """Опрашивает сервер для получения результата по request_id"""
        poll_timeout = 0
        start = time.time()

        while True:
            elapsed_ms = (time.time() - start) * 1000
            if elapsed_ms > self.REQUEST_TIMEOUT_MS:
                logger.error(f"{Colors.RED}Таймаут ожидания результата{Colors.RESET}")
                return None

            poll_timeout = min(poll_timeout + self.POLL_STEP, self.POLL_MAX)
            time.sleep(poll_timeout / 1000)

            try:
                r = self.session.post(
                    self.PROC_URL,
                    data={"c": "get", "requestId": request_id},
                    timeout=self.timeout
                )
                result = r.json()
                state = result.get("state")

                if state == 1:
                    inn = result.get("inn", "")
                    logger.info(f"{Colors.GREEN}ИНН найден: {inn}{Colors.RESET}")
                    return inn
                elif state == 0:
                    logger.warning(f"{Colors.YELLOW}Данные не найдены в базе ФНС{Colors.RESET}")
                    return None
                elif state == -1:
                    continue
                elif state == -2:
                    logger.error(f"{Colors.RED}Сервис временно не доступен{Colors.RESET}")
                    return None
                else:
                    logger.error(f"{Colors.RED}Неизвестное состояние: {state}{Colors.RESET}")
                    return None
            except Exception as e:
                logger.error(f"{Colors.RED}Ошибка при опросе: {e}{Colors.RESET}")
                return None


if __name__ == "__main__":
    print(f"\n{Colors.BOLD}Запуск проверки ИНН через ФНС{Colors.RESET}\n")

    client = NalogInnClient(timeout=30, retries=3, retry_delay=2.0)

    borrower_data = {
        "last_name": "Иванов",
        "first_name": "Иван",
        "patronymic": "Иванович",
        "birth_date": "12.02.1961",
        "passport_series": "1234",
        "passport_number": "123456",
        "passport_issue_date": "01.04.2011"
    }

    inn_result = client.get_inn(**borrower_data)

    print(f"\n{'='*60}")
    if inn_result:
        print(f"{Colors.GREEN}{Colors.BOLD}РЕЗУЛЬТАТ: ИНН = {inn_result}{Colors.RESET}")
    else:
        print(f"{Colors.RED}{Colors.BOLD}РЕЗУЛЬТАТ: Не удалось получить ИНН{Colors.RESET}")
        print(f"{Colors.YELLOW}Совет: Проверьте корректность данных паспорта (формат серии: 4 цифры, номера: 6 цифр){Colors.RESET}")
    print(f"{'='*60}\n")
