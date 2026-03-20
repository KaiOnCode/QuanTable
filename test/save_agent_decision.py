import csv
import re
from datetime import datetime
import uuid
from datetime import datetime

def parse_agent_output(text):
    """解析 agent 的自然语言输出"""

    # 方向
    direction = re.search(r"方向[:：]\s*(\S+)", text)
    direction = direction.group(1) if direction else ""

    # 时间范围
    time_range = re.search(r"时间范围[:：]\s*(\S+)", text)
    time_range = time_range.group(1) if time_range else ""

    # 置信度
    confidence = re.search(r"置信度[:：]\s*([0-9.]+)", text)
    confidence = float(confidence.group(1)) if confidence else ""

    # 一句话总结
    one_sentence = re.search(r"一句话结论[:：]\s*(.+)", text)
    one_sentence = one_sentence.group(1).strip() if one_sentence else ""

    # PM 理由：text内容
    pm_reason = text

    return {
        "direction": direction,
        "time_range": time_range,
        "confidence": confidence,
        "one_sentence": one_sentence,
        "pm_reason": pm_reason
    }


def save_agent_csv(ticker, date_time, agent_text, final_decision, target_pos_pct):
    """解析 agent 文本并写入 CSV"""

    parsed = parse_agent_output(agent_text)
    dt = datetime.fromisoformat(date_time.replace("Z", "+00:00"))
    date_str = dt.strftime("%Y-%m-%d")
    time_str = dt.strftime("%H:%M")
    decision_id = 1

    filename = "agent_decisions.csv"
    write_header = False

    try:
        open(filename, "r").close()
    except FileNotFoundError:
        write_header = True

    with open(filename, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)

        if write_header:
            writer.writerow([
                "date", "time", "ticker", "decision_id",
                "final_decision", "target_pos_pct",
                "direction","time_range", "confidence", "one_sentence", "pm_reason"
            ])

        writer.writerow([
            date_str, time_str, ticker, decision_id,final_decision,target_pos_pct,
            parsed["direction"],
            parsed["time_range"],
            parsed["confidence"],
            parsed["one_sentence"],
            parsed["pm_reason"]
        ])

    print(f"决策已保存到 {filename}，决策ID={decision_id}")
