"""
[INPUT]: 无外部依赖
[OUTPUT]: 对外提供自定义异常类型（BaseError/RepositoryError/BusinessError/LLMError）
[POS]: backend/core 的异常定义模块，被所有需要抛出业务异常的模块消费
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""


# ==================== 基础异常 ====================
class BaseError(Exception):
    """所有自定义异常的父类"""

    pass


# ==================== Repository 层异常 ====================
class RepositoryError(BaseError):
    """数据库操作失败"""

    pass


class DocumentNotFoundError(RepositoryError):
    """文档不存在"""

    pass


class DuplicateKeyError(RepositoryError):
    """唯一索引冲突"""

    pass


# ==================== Service 层异常 ====================
class BusinessError(BaseError):
    """业务逻辑错误"""

    pass


class ResourceNotFoundError(BusinessError):
    """资源不存在（用户/Agent/会话）"""

    pass


class InvalidOperationError(BusinessError):
    """非法操作（如向不存在的会话发消息）"""

    pass


# ==================== LLM 层异常 ====================
class LLMError(BaseError):
    """LLM 调用失败"""

    pass


class OpenAIRateLimitError(LLMError):
    """OpenAI 速率限制"""

    pass


class OpenAIAPIError(LLMError):
    """OpenAI API 通用错误"""

    pass
