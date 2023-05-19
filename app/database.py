from typing import Optional, Any

import pymongo
import uuid
from datetime import datetime

from app import settings


class Database:

    def __init__(self):
        self.client = pymongo.MongoClient(settings.mongodb_uri)
        self.db = self.client["chatgpt_telegram_bot"]

        # models
        self.user = self.db["user"]
        self.dialog = self.db["dialog"]
        self.referral_links = self.db["referral_links"]

    def check_if_user_exists(self, user_id: int, raise_exception: bool = False):
        if self.user.count_documents({"_id": user_id}) > 0:
            return True
        else:
            if raise_exception:
                raise ValueError(f"User {user_id} does not exist")
            else:
                return False

    def add_new_user(
        self,
        user_id: int,
        chat_id: int,
        username: str = "",
        first_name: str = "",
        last_name: str = "",
    ):
        user_dict = {
            "_id": user_id,
            "chat_id": chat_id,

            "username": username,
            "first_name": first_name,
            "last_name": last_name,

            "last_interaction": datetime.now(),
            "first_seen": datetime.now(),

            "current_dialog_id": None,
            "current_chat_mode": "assistant",
            "current_model": settings.models["available_text_models"][0],

            "n_used_tokens": {},
            "n_requests": 0,
            "trial": True,

            "n_generated_images": 0,
            "n_transcribed_seconds": 0.0  # voice message transcription
        }

        if not self.check_if_user_exists(user_id):
            self.user.insert_one(user_dict)

    def start_new_dialog(self, user_id: int):
        self.check_if_user_exists(user_id, raise_exception=True)

        dialog_id = str(uuid.uuid4())
        dialog_dict = {
            "_id": dialog_id,
            "user_id": user_id,
            "chat_mode": self.get_user_attribute(user_id, "current_chat_mode"),
            "start_time": datetime.now(),
            "model": self.get_user_attribute(user_id, "current_model"),
            "messages": []
        }

        # add new dialog
        self.dialog.insert_one(dialog_dict)

        # update user's current dialog
        self.user.update_one(
            {"_id": user_id},
            {"$set": {"current_dialog_id": dialog_id}}
        )

        return dialog_id

    def get_or_create_referral_link(self, user_id: int):
        self.check_if_user_exists(user_id, raise_exception=True)

        link_dict = self.referral_links.find_one({"user_id": user_id})
        if not link_dict:
            link_dict = {
                "user_id": user_id,
                'invited_users': []
            }
            self.referral_links.insert_one(link_dict)
        return link_dict["invited_users"]

    def add_invited_user_in_referral_link(self, owner_id: int, invited_user: int):
        self.check_if_user_exists(invited_user, raise_exception=True)

        if owner_id != invited_user:
            invited_users = self.get_or_create_referral_link(owner_id)
            if invited_user not in invited_users:
                invited_users.append(invited_user)
                self.referral_links.update_one({"user_id": owner_id}, {"$set": {'invited_users': invited_users}})

    def get_user_attribute(self, user_id: int, key: str):
        self.check_if_user_exists(user_id, raise_exception=True)
        user_dict = self.user.find_one({"_id": user_id})

        if key not in user_dict:
            return None

        return user_dict[key]

    def set_user_attribute(self, user_id: int, key: str, value: Any):
        self.check_if_user_exists(user_id, raise_exception=True)
        self.user.update_one({"_id": user_id}, {"$set": {key: value}})

    def update_n_used_tokens(self, user_id: int, model: str, n_input_tokens: int, n_output_tokens: int):
        n_used_tokens_dict = self.get_user_attribute(user_id, "n_used_tokens")

        if model in n_used_tokens_dict:
            n_used_tokens_dict[model]["n_input_tokens"] += n_input_tokens
            n_used_tokens_dict[model]["n_output_tokens"] += n_output_tokens
        else:
            n_used_tokens_dict[model] = {
                "n_input_tokens": n_input_tokens,
                "n_output_tokens": n_output_tokens
            }

        self.set_user_attribute(user_id, "n_used_tokens", n_used_tokens_dict)

        n_requests = self.get_user_attribute(user_id, "n_requests")
        self.set_user_attribute(user_id, "n_requests", n_requests + 1)

    def get_dialog_messages(self, user_id: int, dialog_id: Optional[str] = None):
        self.check_if_user_exists(user_id, raise_exception=True)

        if dialog_id is None:
            dialog_id = self.get_user_attribute(user_id, "current_dialog_id")

        dialog_dict = self.dialog.find_one({"_id": dialog_id, "user_id": user_id})
        return dialog_dict["messages"]

    def set_dialog_messages(self, user_id: int, dialog_messages: list, dialog_id: Optional[str] = None):
        self.check_if_user_exists(user_id, raise_exception=True)

        if dialog_id is None:
            dialog_id = self.get_user_attribute(user_id, "current_dialog_id")

        self.dialog.update_one(
            {"_id": dialog_id, "user_id": user_id},
            {"$set": {"messages": dialog_messages}}
        )
