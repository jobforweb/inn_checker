#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Скрипт для получения ИНН через сервис ФНС
Корректно форматирует серию и номер паспорта
"""

import requests
import time
import logging
from typing import Optional

# ==================== НАСТРОЙКА ЛОГИРОВАНИЯ ====================
LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(message)s"
DATE_FORMAT = "%H:%M:%S"

class Colors:
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    BLUE = "\033[94m"
    RESET = "\033[0m"
    BOLD = "\033[1m"

# Настройка логгера
logging.basicConfig(
    level=logging.INFO,
    format=LOG_FORMAT,
    datefmt=DATE_FORMAT,
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

class NalogInnClient:
    """Клиент для получения ИНН с учётом актуальных требований сервиса ФНС (на 11.04.2026)"""
    
    BASE_URL = "https://service.nalog.ru/inn-proc.do"
    MAIN_PAGE = "https://service.nalog.ru/inn.do"
    
    HEADERS = {
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
        "Connection": "keep-alive",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Origin": "https://service.nalog.ru",
        "Referer": MAIN_PAGE,
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
        "X-Requested-With": "XMLHttpRequest",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    }
    
    def __init__(self, timeout: int = 30, retries: int = 3, retry_delay: float = 2.0):
        self.timeout = timeout
        self.retries = retries
        self.retry_delay = retry_delay
        self.session = requests.Session()
        self.session.headers.update(self.HEADERS)
        
        # Инициализация сессии
        self._init_session()
    
    def _init_session(self) -> bool:
        """Инициализация сессии через GET-запрос к основной странице"""
        try:
            logger.info(f"{Colors.BLUE}→ Загрузка основной страницы: {self.MAIN_PAGE}{Colors.RESET}")
            response = self.session.get(self.MAIN_PAGE, timeout=self.timeout)
            response.raise_for_status()
            
            # Проверяем наличие формы на странице
            if "Узнать ИНН" in response.text or "Фамилия" in response.text:
                logger.info(f"{Colors.GREEN}✓ Сессия успешно инициализирована{Colors.RESET}")
                return True
            else:
                logger.warning(f"{Colors.YELLOW}⚠️ Страница загружена, но форма не найдена{Colors.RESET}")
                return False
                
        except Exception as e:
            logger.error(f"{Colors.RED}✗ Ошибка инициализации сессии: {str(e)}{Colors.RESET}")
            return False
    
    def _prepare_docno(self, series: str, number: str) -> str:
        """
        Форматирует серию и номер паспорта в требуемый формат XX XX XXXXXX
        
        ВАЖНО: Сервис ФНС требует формат "99 99 9999990", где:
        - первые 2 цифры - первая часть серии
        - следующие 2 цифры - вторая часть серии
        - 6 цифр - номер документа
        """
        series_clean = ''.join(filter(str.isdigit, str(series)))
        number_clean = ''.join(filter(str.isdigit, str(number)))
        
        # Проверка длины серии (должно быть 4 цифры)
        if len(series_clean) < 4:
            logger.error(f"{Colors.RED}✗ Некорректная серия паспорта: '{series_clean}' (требуется 4 цифры){Colors.RESET}")
            raise ValueError("Серия паспорта должна содержать 4 цифры")
        
        # Проверка длины номера (должно быть 6 цифр)
        if len(number_clean) < 6:
            logger.error(f"{Colors.RED}✗ Некорректный номер паспорта: '{number_clean}' (требуется 6 цифр){Colors.RESET}")
            raise ValueError("Номер паспорта должен содержать 6 цифр")
        
        # Форматируем как "XX XX XXXXXX"
        formatted = f"{series_clean[:2]} {series_clean[2:4]} {number_clean[:6]}"
        logger.debug(f"Форматирование паспорта: '{series}'+'{number}' → '{formatted}'")
        return formatted
    
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
        Запрашивает ИНН по данным физического лица с учётом актуальных требований
        
        :param passport_issue_date: Дата выдачи паспорта (ДД.ММ.ГГГГ) - обязательна
        :return: ИНН или None
        """
        # Подготовка данных формы
        form_data = {
            "c": "innMy",
            "captcha": "",
            "captchaToken": "",
            "fam": last_name.strip(),
            "nam": first_name.strip(),
            "otch": patronymic.strip() if patronymic else "",
            "bdate": birth_date,
            "doctype": "21",  # Паспорт РФ
            "docno": self._prepare_docno(passport_series, passport_number),
            "docdt": passport_issue_date
        }
        
        logger.info(f"{Colors.BLUE}🔍 Запрос ИНН: {last_name} {first_name} {patronymic} | "
                   f"Дата рождения: {birth_date} | Паспорт: {passport_series}******{Colors.RESET}")
        
        for attempt in range(self.retries):
            try:
                start_time = time.time()
                response = self.session.post(
                    self.BASE_URL,
                    data=form_data,
                    timeout=self.timeout
                )
                elapsed = time.time() - start_time
                
                logger.debug(f"← HTTP {response.status_code} за {elapsed:.2f}с")
                
                if response.status_code != 200:
                    logger.error(f"{Colors.RED}✗ HTTP {response.status_code}: {response.text[:200]}{Colors.RESET}")
                    return None
                
                try:
                    result = response.json()
                    logger.debug(f"JSON ответ: {result}")
                    
                    if "ERRORS" in result and "docno" in result["ERRORS"]:
                        logger.error(f"{Colors.RED}✗ Ошибка валидации: {result['ERRORS']['docno'][0][:100]}{Colors.RESET}")
                        return None
                    
                    if result.get("captchaRequired", False):
                        logger.warning(f"{Colors.YELLOW}⚠️ Требуется CAPTCHA — автоматический запрос невозможен{Colors.RESET}")
                        return None
                    
                    if result.get("code") == 1:
                        inn = result.get("inn", "")
                        logger.info(f"{Colors.GREEN}✓ ИНН найден: {inn}{Colors.RESET}")
                        return inn
                    elif result.get("code") == 0:
                        logger.warning(f"{Colors.YELLOW}⚠️ Данные не найдены в базе ФНС{Colors.RESET}")
                        return None
                    else:
                        logger.warning(f"{Colors.YELLOW}⚠️ Неизвестный код ответа: {result.get('code')}{Colors.RESET}")
                        return None
                
                except ValueError:
                    logger.error(f"{Colors.RED}✗ Ошибка парсинга JSON: {response.text[:200]}{Colors.RESET}")
                    return None
                    
            except requests.exceptions.RequestException as e:
                logger.error(f"{Colors.RED}✗ Ошибка запроса (попытка {attempt+1}): {str(e)}{Colors.RESET}")
            
            # Задержка перед повторной попыткой
            if attempt < self.retries - 1:
                delay = self.retry_delay * (attempt + 1)
                logger.info(f"{Colors.BLUE}⏳ Повтор через {delay}с...{Colors.RESET}")
                time.sleep(delay)
        
        return None


# ==================== ПРИМЕР ИСПОЛЬЗОВАНИЯ ====================
if __name__ == "__main__":
    print(f"\n{Colors.BOLD}🚀 Запуск проверки ИНН через ФНС {Colors.RESET}\n")
    
    # Инициализация клиента
    client = NalogInnClient(timeout=30, retries=3, retry_delay=2.0)
    
    # Данные физического лица
    borrower_data = {
        "last_name": "Иванов",
        "first_name": "Иван",
        "patronymic": "Иванович",
        "birth_date": "12.02.1961",
        "passport_series": "1234",
        "passport_number": "123456",
        "passport_issue_date": "01.04.2011"
    }
    
    # Выполнение запроса
    inn_result = client.get_inn(**borrower_data)
    
    # Финальный вывод
    print(f"\n{'='*60}")
    if inn_result:
        print(f"{Colors.GREEN}{Colors.BOLD}🎯 РЕЗУЛЬТАТ: ИНН = {inn_result}{Colors.RESET}")
    else:
        print(f"{Colors.RED}{Colors.BOLD}🎯 РЕЗУЛЬТАТ: Не удалось получить ИНН{Colors.RESET}")
        print(f"{Colors.YELLOW}💡 Совет: Проверьте корректность данных паспорта (формат серии: 4 цифры, номера: 6 цифр){Colors.RESET}")
    print(f"{'='*60}\n")