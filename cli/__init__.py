"""
[INPUT]: 无外部依赖（包初始化文件）
[OUTPUT]: 对外提供 cli 包命名空间
[POS]: cli 包的根模块，供 pyproject.toml 的 [project.scripts] 引用 cli.main:app
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""
