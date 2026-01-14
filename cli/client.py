"""
[INPUT]: 依赖 httpx 的 Client，依赖 typing 的类型注解
[OUTPUT]: 对外提供 APIClient 类，封装与后端 API 的 HTTP 交互
[POS]: cli 的 HTTP 客户端，被所有 commands 模块消费
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

import httpx
from typing import Dict, Any, List, Optional


class APIClient:
    """HTTP 客户端封装

    提供与后端 API 交互的所有方法
    """

    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url.rstrip("/")
        self.client = httpx.Client(base_url=self.base_url, timeout=30.0)

    def close(self):
        """关闭客户端"""
        self.client.close()

    # ==================== 用户管理 ====================
    def create_user(self, username: str) -> Dict[str, Any]:
        """创建用户"""
        response = self.client.post("/api/users", json={"username": username})
        response.raise_for_status()
        return response.json()

    def list_users(self) -> List[Dict[str, Any]]:
        """列出所有用户"""
        response = self.client.get("/api/users")
        response.raise_for_status()
        return response.json()

    # ==================== Agent 管理 ====================
    def create_agent(
        self, name: str, system_prompt: str, model: str = "gpt-4o-mini"
    ) -> Dict[str, Any]:
        """创建 Agent"""
        response = self.client.post(
            "/api/agents",
            json={"name": name, "system_prompt": system_prompt, "model": model},
        )
        response.raise_for_status()
        return response.json()

    def list_agents(self) -> List[Dict[str, Any]]:
        """列出所有 Agent"""
        response = self.client.get("/api/agents")
        response.raise_for_status()
        return response.json()

    # ==================== 会话管理 ====================
    def create_conversation(
        self, user_id: str, agent_id: str, title: Optional[str] = None
    ) -> Dict[str, Any]:
        """创建会话"""
        data = {"user_id": user_id, "agent_id": agent_id}
        if title:
            data["title"] = title
        response = self.client.post("/api/conversations", json=data)
        response.raise_for_status()
        return response.json()

    def list_conversations(self, user_id: str) -> List[Dict[str, Any]]:
        """列出用户的所有会话"""
        response = self.client.get("/api/conversations", params={"user_id": user_id})
        response.raise_for_status()
        return response.json()

    # ==================== 消息与对话 ====================
    def send_message(self, conv_id: str, content: str) -> Dict[str, Any]:
        """发送消息并获取回复"""
        response = self.client.post(
            f"/api/conversations/{conv_id}/chat", json={"content": content}
        )
        response.raise_for_status()
        return response.json()

    def get_messages(self, conv_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """获取对话历史"""
        response = self.client.get(
            f"/api/conversations/{conv_id}/messages", params={"limit": limit}
        )
        response.raise_for_status()
        return response.json()
