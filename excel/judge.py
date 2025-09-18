import os
import re
import csv
import pandas as pd
from difflib import SequenceMatcher
from typing import Dict, Any

CSV_PATH = "chat_history_all.csv"
OUT_DIR = "./eval_output"
os.makedirs(OUT_DIR, exist_ok=True)

THRESHOLDS = {
    "correct": 0.60,  # 降低阈值
    "partial": 0.40,  # 降低阈值
    "numeric_tol_rel": 1e-3,
    "numeric_tol_abs": 1e-2,
    "list_match_threshold": 0.7,  # 降低列表匹配阈值
}

def safe_str(x: Any) -> str:
    return "" if pd.isna(x) else str(x)

def normalize_date(s: str) -> str:
    """将中文日期格式（如2025年6月27日）转换为标准格式（如2025-06-27）。"""
    s = safe_str(s)
    date_pattern = r'(\d{4})年(\d{1,2})月(\d{1,2})日'
    return re.sub(date_pattern, r'\1-\2-\3', s)

def normalize_text(s: str) -> str:
    """保留中文和英文，规范化文本，处理日期和数值格式。"""
    s = safe_str(s).strip()
    s = normalize_date(s)
    s = re.sub(r"[,\uFF0C;；和&]", " ", s)
    s = re.sub(r"[年月日]", "-", s)
    s = re.sub(r"(查询结果显示|任务执行完成|分别为|如下|的订单数量为|其得分为)", "", s)  # 移除更多无关词
    s = re.sub(r"\.0\b", "", s)  # 统一浮点数格式（如88.0→88）
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"[^\w\u4e00-\u9fff%\.\-\/\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s.lower()

def is_contained(exp_raw: str, ai_raw: str) -> bool:
    """检查标准答案是否包含在AI答案中，忽略标点、连接词和格式差异。"""
    exp_clean = normalize_text(exp_raw)
    ai_clean = normalize_text(ai_raw)
    return exp_clean in ai_clean

def is_list_match(exp_raw: str, ai_raw: str) -> tuple[bool, float]:
    """检查列表型答案是否内容一致（忽略顺序），返回是否匹配及Jaccard相似度。"""
    exp_clean = normalize_text(exp_raw)
    ai_clean = normalize_text(ai_raw)
    # 分割为键值对
    exp_items = set(re.split(r'\s+|[-]', exp_clean))
    ai_items = set(re.split(r'\s+|[-]', ai_clean))
    # 计算Jaccard相似度
    intersection = len(exp_items & ai_items)
    union = len(exp_items | ai_items)
    jaccard = intersection / union if union else 0.0
    is_match = jaccard >= THRESHOLDS["list_match_threshold"]
    return is_match, jaccard

def extract_relevant_text(ai_raw: str, exp_raw: str) -> str:
    """提取AI答案中与标准答案相关的核心内容，处理键值对。"""
    norm_exp = normalize_text(exp_raw)
    keywords = set(re.split(r'\s+|[-]', norm_exp))
    norm_ai = normalize_text(ai_raw)
    # 按键值对分割
    ai_items = re.split(r'\s+|[-]', norm_ai)
    relevant_items = [item for item in ai_items if item in keywords]
    return ' '.join(relevant_items) if relevant_items else norm_ai

NUMBER_RE = re.compile(r'[-+]?\d*\.\d+|[-+]?\d+')

def extract_numbers(s: str) -> list:
    """提取数值，确保重复数值正确处理。"""
    s = s.replace(",", "")
    nums = NUMBER_RE.findall(s)
    return [float(x) for x in nums] if nums else []

def is_close_num(a: float, b: float) -> bool:
    return abs(a - b) <= max(THRESHOLDS["numeric_tol_abs"], abs(b) * THRESHOLDS["numeric_tol_rel"])

def seq_ratio(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()

def token_jaccard(a: str, b: str) -> float:
    sa, sb = set(a.split()), set(b.split())
    return len(sa & sb) / len(sa | sb) if sa and sb else 0.0

def evaluate_row(ai: str, expected: str) -> Dict[str, Any]:
    ai_raw, exp_raw = safe_str(ai), safe_str(expected)

    # --- 特殊规则：短答案包含判断 ---
    if exp_raw and is_contained(exp_raw, ai_raw):
        return {
            "ai_answer": ai_raw,
            "expected_answer": exp_raw,
            "verdict": "正确",
            "combined_score": 1.0,
            "seq_ratio": 1.0,
            "issues": ""
        }

    # --- 特殊规则：列表匹配 ---
    is_match, list_jaccard = is_list_match(exp_raw, ai_raw)
    if is_match:
        return {
            "ai_answer": ai_raw,
            "expected_answer": exp_raw,
            "verdict": "正确",
            "combined_score": 1.0,
            "seq_ratio": 1.0,
            "issues": "顺序可能不同但内容一致"
        }

    norm_exp = normalize_text(exp_raw)
    norm_ai = extract_relevant_text(ai_raw, exp_raw)
    nums_ai, nums_exp = extract_numbers(ai_raw), extract_numbers(exp_raw)

    ratio = seq_ratio(norm_ai, norm_exp)
    jacc = token_jaccard(norm_ai, norm_exp)
    issues, numeric_match = [], None

    # 数值匹配
    if nums_exp:
        matched_nums = []
        ai_nums_copy = nums_ai.copy()
        for e in nums_exp:
            for a in ai_nums_copy:
                if is_close_num(a, e):
                    matched_nums.append(a)
                    ai_nums_copy.remove(a)
                    break
        num_score = min(1.0, len(matched_nums) / len(nums_exp)) if nums_exp else 0.5
        numeric_match = len(matched_nums) == len(nums_exp)
        if not numeric_match:
            issues.append(f"数值部分匹配（{len(matched_nums)}/{len(nums_exp)}）")
    else:
        num_score = 0.5

    # 诊断
    if not norm_ai:
        issues.append("AI答案为空")
    elif len(norm_ai.split()) < len(norm_exp.split()) * 0.5:
        issues.append("AI答案明显过短（可能信息缺失）")
    elif len(norm_ai.split()) > len(norm_exp.split()) * 3.0:
        issues.append("AI答案包含过多额外信息")
    if set(norm_ai.split()) != set(norm_exp.split()) and list_jaccard > 0.5:
        issues.append("部分匹配（可能遗漏元素）")
    elif set(norm_ai.split()) == set(norm_exp.split()) and ratio < 0.8:
        issues.append("顺序差异")

    # 数值完全匹配优先
    if nums_exp and numeric_match:
        return {
            "ai_answer": ai_raw,
            "expected_answer": exp_raw,
            "verdict": "正确",
            "combined_score": 1.0,
            "seq_ratio": 1.0,
            "issues": "数值完全匹配"
        }

    # 综合打分
    combined = ratio * 0.2 + jacc * 0.15 + num_score * 0.45 + list_jaccard * 0.2

    if combined >= THRESHOLDS["correct"]:
        verdict = "正确"
    elif combined >= THRESHOLDS["partial"]:
        verdict = "部分正确"
    else:
        verdict = "错误"

    return {
        "ai_answer": ai_raw,
        "expected_answer": exp_raw,
        "verdict": verdict,
        "combined_score": round(combined, 4),
        "seq_ratio": round(ratio, 4),
        "issues": "; ".join(issues)
    }

def evaluate_csv(path: str) -> pd.DataFrame:
    df = pd.read_csv(path).fillna("")
    results = []
    for idx, row in df.iterrows():
        row_id = row.get("id", f"row_{idx+1}") or f"row_{idx+1}"
        res = evaluate_row(row.get("content", ""), row.get("expected_answer", ""))
        results.append({
            "id": row_id,
            "file_name": row.get("file_name", ""),
            **res
        })
    return pd.DataFrame(results)

def summarize_and_write(res_df: pd.DataFrame):
    total = len(res_df)
    correct, partial, wrong = (res_df["verdict"] == "正确").sum(), (res_df["verdict"] == "部分正确").sum(), (res_df["verdict"] == "错误").sum()
    avg_score = res_df["combined_score"].mean().round(4)
    accuracy = round(correct / total * 100, 2) if total else 0.0

    issue_list = res_df["issues"].str.split("; ").explode().dropna().str.strip()
    issue_list = issue_list[issue_list != ""]
    issue_counts = issue_list.value_counts().to_dict()

    res_df.to_csv(os.path.join(OUT_DIR, "detailed_results.csv"), index=False, quoting=csv.QUOTE_ALL)

    md_lines = [
        "## 评估报告\n",
        "### 准确率统计",
        f"- 总任务数: {total}",
        f"- 正确任务数: {correct}",
        f"- 错误任务数: {wrong}",
        f"- 部分正确: {partial}",
        f"- 平均分: {avg_score}",
        f"- 准确率: {accuracy}%\n",
        "### 代表性正确案例"
    ]
    for _, r in res_df[res_df["verdict"] == "正确"].head(5).iterrows():
        md_lines += [
            f"- [{r['id']}] AI答案: \n\n{r['ai_answer']}",
            f"  - 标准答案: {r['expected_answer']}",
            f"  - 说明: 判定为{r['verdict']}（score={r['combined_score']}, seq_ratio={r['seq_ratio']})\n"
        ]
    md_lines.append("### 代表性错误案例")
    for _, r in res_df[res_df["verdict"] == "错误"].head(5).iterrows():
        md_lines += [
            f"- [{r['id']}] AI答案: \n\n{r['ai_answer']}",
            f"  - 标准答案: {r['expected_answer']}",
            f"  - 说明: {r['issues']} (score={r['combined_score']}, seq_ratio={r['seq_ratio']})\n"
        ]
    md_lines.append("### 代表性部分正确案例")
    for _, r in res_df[res_df["verdict"] == "部分正确"].head(5).iterrows():
        md_lines += [
            f"- [{r['id']}] AI答案: \n\n{r['ai_answer']}",
            f"  - 标准答案: {r['expected_answer']}",
            f"  - 说明: {r['issues']} (score={r['combined_score']}, seq_ratio={r['seq_ratio']})\n"
        ]
    md_lines.append("### 全部题目结果")
    for _, r in res_df.iterrows():
        md_lines += [
            f"- [{r['id']}] (文件: {r['file_name']})",
            f"  - AI答案: {r['ai_answer']}",
            f"  - 标准答案: {r['expected_answer']}",
            f"  - 判定: {r['verdict']}",
            f"  - score={r['combined_score']}, seq_ratio={r['seq_ratio']}, issues={r['issues']}\n"
        ]
    md_lines.append("### 错误类型总结")
    for issue, cnt in issue_counts.items():
        md_lines.append(f"- {issue}: {cnt} 次")

    with open(os.path.join(OUT_DIR, "evaluation_report.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines))

if __name__ == "__main__":
    df_res = evaluate_csv(CSV_PATH)
    summarize_and_write(df_res)
    print("评估完成，结果已保存到 eval_output/")