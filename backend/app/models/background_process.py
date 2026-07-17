"""后台进程注册表(全盘进程管理器)。

病根:放后台进程(队列executor/模型服务screen/LibreOffice转换/沙盒/ASR子进程/nohup脚本)
从不统一登记,找bug靠 ps grep 瞎翻。收口成一张表:谁放后台进程就登记
PID/标识符/类型/命令/日志路径/启动时间,退出标状态。查一张表就知道谁是谁、日志在哪。
与资源底座配对:资源底座=机器剩多少力,本表=力被谁占了、日志在哪。
"""
from sqlalchemy import BigInteger, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class BackgroundProcess(Base, TimestampMixin):
    __tablename__ = "framework_background_processes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # 语义标识符:如"模型-qwen3vl"/"回填-fusion-shard0"/"转换-libreoffice"。人一眼看懂是谁
    label: Mapped[str] = mapped_column(String(128), default="", index=True)
    pid: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    # 类型:queue(队列executor)/model(模型服务)/convert(文档转换)/sandbox/script(脚本)/screen(会话)/other
    kind: Mapped[str] = mapped_column(String(32), default="other", index=True)
    # 谁放的:模块名或来源(如 knowledge/model_watchdog/task_dispatcher/manual)
    source: Mapped[str] = mapped_column(String(64), default="")
    command: Mapped[str] = mapped_column(Text, default="")
    log_path: Mapped[str] = mapped_column(Text, default="")
    # 状态:running/exited/killed/stale(pid没了但没正常注销)
    status: Mapped[str] = mapped_column(String(16), default="running", index=True)
    exit_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    started_at: Mapped["DateTime"] = mapped_column(DateTime(timezone=True), nullable=True)
    heartbeat_at: Mapped["DateTime"] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped["DateTime"] = mapped_column(DateTime(timezone=True), nullable=True)
    note: Mapped[str] = mapped_column(Text, default="")
    # 关联(可选):队列任务id等,便于溯源
    ref_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    # 稳定标识符(uuid):进程自己的id,不随PID变。找回/判活靠它,不靠会被回收复用的PID
    run_token: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    # 进程创建时间戳:巡检比对,PID被系统回收给别人时能认出原进程已暴毙
    pid_create_time: Mapped[float | None] = mapped_column(Float, nullable=True)
