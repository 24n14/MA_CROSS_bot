"""
Модуль для логирования API запросов к Bybit
Использует перехват через monkey-patching методов HTTP клиента
"""
import json
import time
from functools import wraps
from typing import Dict, Any, Optional, Callable
from loguru import logger
from pybit.unified_trading import HTTP


class APILogger:
    """
    Класс для логирования API запросов и ответов
    Работает через обертку методов HTTP клиента
    """

    def __init__(self, log_full_response: bool = True, log_params: bool = True):
        """
        Args:
            log_full_response: Логировать ли полный ответ или только статус
            log_params: Логировать ли параметры запроса
        """
        self.log_full_response = log_full_response
        self.log_params = log_params
        self._client = None
        self._original_methods = {}

    def wrap_client(self, client: HTTP) -> HTTP:
        """
        Обертывает клиент pybit для логирования всех запросов

        Args:
            client: Экземпляр HTTP клиента pybit

        Returns:
            Обернутый клиент
        """
        self._client = client

        # Получаем все публичные методы клиента
        methods_to_wrap = [
            'place_order',
            'amend_order',
            'cancel_order',
            'cancel_all_orders',
            'get_open_orders',
            'get_order_history',
            'get_positions',
            'set_leverage',
            'set_trading_stop',
            'get_wallet_balance',
            'get_instruments_info',
            'get_orderbook',
            'get_tickers',
            'get_kline',
            'get_recent_trade',
            'get_open_interest',
            'get_funding_history',
            'set_tpsl_mode',
            'switch_isolated',
            'switch_mode',
            'set_risk_limit',
            'set_auto_add_margin',
            'get_execution_list',
            'get_closed_pnl',
            'get_fee_rate',
            'get_transaction_log'
        ]

        # Обертываем каждый метод
        for method_name in methods_to_wrap:
            if hasattr(client, method_name):
                original_method = getattr(client, method_name)
                if callable(original_method):
                    wrapped_method = self._create_wrapper(method_name, original_method)
                    setattr(client, method_name, wrapped_method)
                    self._original_methods[method_name] = original_method
                    logger.debug(f"🔍 Обернут метод: {method_name}")

        logger.info("🔍 API Logger initialized - все методы обернуты")
        return client

    def _create_wrapper(self, method_name: str, original_method: Callable) -> Callable:
        """
        Создает обертку для метода с логированием

        Args:
            method_name: Имя метода
            original_method: Оригинальный метод

        Returns:
            Обернутый метод
        """

        @wraps(original_method)
        def wrapper(*args, **kwargs):
            # Подготавливаем параметры для логирования
            log_params = self._prepare_log_params(kwargs)

            # Логируем запрос
            self._log_request(method_name, log_params)

            start_time = time.time()

            try:
                # Выполняем оригинальный метод
                result = original_method(*args, **kwargs)
                elapsed_ms = (time.time() - start_time) * 1000

                # Логируем ответ
                self._log_response(method_name, result, elapsed_ms)

                # Проверяем наличие ошибки
                if isinstance(result, dict):
                    ret_code = result.get('retCode', 0)
                    if ret_code != 0:
                        ret_msg = result.get('retMsg', 'Unknown error')
                        logger.error(f"❌ API Error [{method_name}]: retCode={ret_code}, retMsg={ret_msg}")

                        # Подробное логирование ошибки
                        logger.error(f"📝 Full error response: {json.dumps(result, indent=2, ensure_ascii=False)}")

                return result

            except Exception as e:
                elapsed_ms = (time.time() - start_time) * 1000
                logger.error(f"""
❌ API REQUEST FAILED [{method_name}]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Error: {str(e)}
Elapsed: {elapsed_ms:.2f}ms
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
""")
                raise

        return wrapper

    def _prepare_log_params(self, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Подготавливает параметры для логирования, скрывая чувствительные данные

        Args:
            kwargs: Параметры метода

        Returns:
            Очищенные параметры
        """
        if not self.log_params:
            return {"log_params": "disabled"}

        clean_params = {}
        sensitive_fields = ['api_key', 'apiKey', 'secret', 'sign', 'signature', 'password', 'token']

        for key, value in kwargs.items():
            if key in sensitive_fields:
                clean_params[key] = '***HIDDEN***'
            elif isinstance(value, dict):
                clean_params[key] = self._clean_dict(value)
            elif isinstance(value, list):
                clean_params[key] = self._clean_list(value)
            else:
                clean_params[key] = value

        return clean_params

    def _clean_dict(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Рекурсивно очищает словарь от чувствительных данных"""
        if not isinstance(data, dict):
            return data

        sensitive_fields = ['api_key', 'apiKey', 'secret', 'sign', 'signature', 'password', 'token']
        clean = {}

        for key, value in data.items():
            if key in sensitive_fields:
                clean[key] = '***HIDDEN***'
            elif isinstance(value, dict):
                clean[key] = self._clean_dict(value)
            elif isinstance(value, list):
                clean[key] = self._clean_list(value)
            else:
                clean[key] = value

        return clean

    def _clean_list(self, data: list) -> list:
        """Рекурсивно очищает список от чувствительных данных"""
        if not isinstance(data, list):
            return data

        clean = []
        for item in data:
            if isinstance(item, dict):
                clean.append(self._clean_dict(item))
            elif isinstance(item, list):
                clean.append(self._clean_list(item))
            else:
                clean.append(item)
        return clean

    def _log_request(self, method_name: str, params: Dict[str, Any]):
        """
        Логирует API запрос

        Args:
            method_name: Имя метода
            params: Параметры запроса
        """
        params_str = json.dumps(params, indent=2, ensure_ascii=False) if params else "{}"

        # Ограничиваем длину лога
        if len(params_str) > 2000:
            params_str = params_str[:2000] + "... (truncated)"

        logger.debug(f"""
📤 API REQUEST: {method_name}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Params: {params_str}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
""")

    def _log_response(self, method_name: str, response: Any, elapsed_ms: float):
        """
        Логирует ответ API

        Args:
            method_name: Имя метода
            response: Ответ от API
            elapsed_ms: Время выполнения в миллисекундах
        """
        if self.log_full_response:
            if isinstance(response, dict):
                # Очищаем ответ от чувствительных данных
                clean_response = self._clean_dict(response)
                response_str = json.dumps(clean_response, indent=2, ensure_ascii=False)
            else:
                response_str = str(response)

            # Ограничиваем длину лога
            if len(response_str) > 3000:
                response_str = response_str[:3000] + "... (truncated)"

            logger.debug(f"""
📥 API RESPONSE: {method_name}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Elapsed: {elapsed_ms:.2f}ms
Response: {response_str}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
""")
        else:
            ret_code = response.get('retCode', 'N/A') if isinstance(response, dict) else 'N/A'
            logger.debug(f"""
📥 API RESPONSE: {method_name}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Elapsed: {elapsed_ms:.2f}ms
Status: retCode={ret_code}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
""")


class APIRequestLogger:
    """
    Класс-декоратор для логирования API запросов
    """

    def __init__(self, client: HTTP, log_full_response: bool = True):
        """
        Args:
            client: Экземпляр HTTP клиента pybit
            log_full_response: Логировать ли полный ответ
        """
        self.client = client
        self.log_full_response = log_full_response
        self._wrap_methods()

    def _wrap_methods(self):
        """Обертывает все методы клиента"""
        methods_to_wrap = [
            'place_order',
            'amend_order',
            'cancel_order',
            'cancel_all_orders',
            'get_open_orders',
            'get_order_history',
            'get_positions',
            'set_leverage',
            'set_trading_stop',
            'get_wallet_balance',
            'get_instruments_info',
            'get_orderbook',
            'get_tickers',
            'get_kline',
            'get_recent_trade',
            'get_open_interest',
            'get_funding_history'
        ]

        for method_name in methods_to_wrap:
            if hasattr(self.client, method_name):
                original = getattr(self.client, method_name)
                if callable(original):
                    wrapped = self._create_decorator(method_name, original)
                    setattr(self.client, method_name, wrapped)

    def _create_decorator(self, method_name: str, func: Callable) -> Callable:
        """Создает декоратор для метода"""

        @wraps(func)
        def wrapper(*args, **kwargs):
            # Логируем вызов
            logger.debug(f"🔄 Calling {method_name}")

            # Логируем параметры
            if kwargs:
                clean_kwargs = {}
                for key, value in kwargs.items():
                    if key in ['api_key', 'api_secret', 'secret', 'password']:
                        clean_kwargs[key] = '***HIDDEN***'
                    elif isinstance(value, dict):
                        clean_kwargs[key] = APILogger()._clean_dict(value)
                    else:
                        clean_kwargs[key] = value

                logger.debug(f"📝 {method_name} params: {json.dumps(clean_kwargs, indent=2, ensure_ascii=False)}")

            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                elapsed = (time.time() - start_time) * 1000

                if isinstance(result, dict):
                    ret_code = result.get('retCode', 0)
                    logger.debug(f"✅ {method_name} completed: retCode={ret_code}, elapsed={elapsed:.2f}ms")

                    if self.log_full_response and ret_code != 0:
                        logger.error(f"❌ {method_name} error: {result.get('retMsg', 'Unknown')}")
                else:
                    logger.debug(f"✅ {method_name} completed: elapsed={elapsed:.2f}ms")

                return result
            except Exception as e:
                elapsed = (time.time() - start_time) * 1000
                logger.error(f"❌ {method_name} failed: {str(e)}, elapsed={elapsed:.2f}ms")
                raise

        return wrapper


def create_logged_session(api_key: str, api_secret: str, demo: bool = True, **kwargs) -> HTTP:
    """
    Создает сессию Pybit с логированием

    Args:
        api_key: API ключ
        api_secret: API секрет
        demo: Демо-режим
        **kwargs: Дополнительные параметры для HTTP

    Returns:
        HTTP клиент с логированием
    """
    # Создаем клиент
    client = HTTP(
        api_key=api_key,
        api_secret=api_secret,
        demo=demo,
        **kwargs
    )

    # Обертываем для логирования
    logger.info("🔍 API Logger initialized")
    return APILogger(log_full_response=True).wrap_client(client)


# === Упрощенная версия для быстрого использования ===
class SimpleAPILogger:
    """
    Простая версия логгера API запросов
    Использует декоратор для обертывания методов
    """

    @staticmethod
    def log_request(func):
        """Декоратор для логирования запросов"""

        @wraps(func)
        def wrapper(*args, **kwargs):
            method_name = func.__name__

            # Логируем вызов
            logger.info(f"🔄 API Call: {method_name}")

            # Логируем параметры (без чувствительных данных)
            if kwargs:
                clean_kwargs = {}
                sensitive = ['api_key', 'api_secret', 'secret', 'password', 'sign']
                for key, value in kwargs.items():
                    if key in sensitive:
                        clean_kwargs[key] = '***HIDDEN***'
                    else:
                        clean_kwargs[key] = value
                logger.debug(f"📝 {method_name} params: {json.dumps(clean_kwargs, indent=2, ensure_ascii=False)}")

            start = time.time()
            try:
                result = func(*args, **kwargs)
                elapsed = (time.time() - start) * 1000

                # Логируем результат
                if isinstance(result, dict):
                    ret_code = result.get('retCode', 0)
                    if ret_code == 0:
                        logger.info(f"✅ {method_name} success: elapsed={elapsed:.2f}ms")
                    else:
                        logger.error(f"❌ {method_name} error: retCode={ret_code}, msg={result.get('retMsg')}")
                else:
                    logger.info(f"✅ {method_name} completed: elapsed={elapsed:.2f}ms")

                return result
            except Exception as e:
                elapsed = (time.time() - start) * 1000
                logger.error(f"❌ {method_name} exception: {str(e)}, elapsed={elapsed:.2f}ms")
                raise

        return wrapper