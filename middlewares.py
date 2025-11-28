"""
Middleware для проверки различных условий перед обработкой сообщений.
"""

from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import Message

from config import ADMIN_CHAT, REQUIRED_CHANNELS, logger
from database import User, user_exists
from handlers.subscription_handlers import send_subscription_request


class SubscriptionMiddleware(BaseMiddleware):
    """
    Middleware для проверки подписки пользователя на обязательные каналы.
    Если пользователь не подписан, показывает сообщение с просьбой подписаться.
    """
    
    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: Dict[str, Any]
    ) -> Any:
        """
        Проверяет подписку перед обработкой сообщения.
        
        Args:
            handler: Следующий обработчик в цепочке
            event: Сообщение от пользователя
            data: Дополнительные данные
        """
        # Пропускаем проверку для админ-чата
        if event.chat.id == ADMIN_CHAT:
            return await handler(event, data)
        
        # Пропускаем проверку если нет обязательных каналов
        if not REQUIRED_CHANNELS:
            return await handler(event, data)
        
        # Пропускаем проверку для callback_query (они обрабатываются отдельно)
        if not isinstance(event, Message):
            return await handler(event, data)
        
        # Проверяем, существует ли пользователь в БД
        user_id = event.from_user.id
        if not await user_exists(user_id):
            # Пользователь еще не зарегистрирован, пропускаем проверку
            # (регистрация покажет сообщение о подписке)
            return await handler(event, data)
        
        # Получаем пользователя из БД
        user = User(user_id)
        await user.get_from_db()
        
        # Проверяем статус подписки
        if user.subscription_verified == 0:
            # Пользователь не подписан
            logger.info(f"USER{user_id}: попытка использования бота без подписки")
            
            # Отправляем сообщение с просьбой подписаться
            await send_subscription_request(event.chat.id, event.message_id)
            
            # Прерываем обработку
            return
        
        # Если subscription_verified == 1 или NULL, продолжаем обработку
        return await handler(event, data)

