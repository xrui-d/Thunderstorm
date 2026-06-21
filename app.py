import os
import json
import re
from pathlib import Path
from datetime import datetime

import streamlit as st
from dotenv import load_dotenv
from openai import OpenAI


# ============================================================
# Page settings
# ============================================================
st.set_page_config(
    page_title="Thunderstorm Interactive Archive",
    page_icon="⛈️",
    layout="wide",
)


# ============================================================
# API setup
# ============================================================
load_dotenv()

api_key = os.getenv("OPENAI_API_KEY")

if not api_key:
    try:
        api_key = st.secrets["OPENAI_API_KEY"]
    except Exception:
        api_key = None

client = OpenAI(api_key=api_key) if api_key else None


DEFAULT_MODEL = "gpt-4.1-mini"


# ============================================================
# Basic helpers
# ============================================================
def load_json(file_path: str) -> dict:
    path = Path(file_path)

    if not path.exists():
        return {}

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        st.error(f"{file_path} 格式有问题：{e}")
        return {}


def safe_join(items, sep="、") -> str:
    if not items:
        return "暂无资料"
    return sep.join([str(x) for x in items])


def format_list(items) -> str:
    if not items:
        return "暂无资料"
    return "\n".join([f"- {item}" for item in items])


def show_list(items):
    if not items:
        st.write("暂无资料")
    else:
        for item in items:
            st.write(f"- {item}")


def score_to_label(score: int) -> str:
    if score >= 9:
        return "极高"
    if score >= 7:
        return "高"
    if score >= 5:
        return "中等"
    if score >= 3:
        return "较低"
    return "低"


def escape_dot(text: str) -> str:
    return str(text).replace('"', '\\"')


def section_is_unlocked(reveal_from: str, current_section: str, section_names: list) -> bool:
    if reveal_from not in section_names:
        return True
    if current_section not in section_names:
        return True
    return section_names.index(reveal_from) <= section_names.index(current_section)


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def init_session_state():
    if "analysis_history" not in st.session_state:
        st.session_state.analysis_history = []

    if "extra_snippets" not in st.session_state:
        st.session_state.extra_snippets = []

    if "model_name" not in st.session_state:
        st.session_state.model_name = DEFAULT_MODEL


# ============================================================
# Evidence / snippets
# ============================================================
def normalize_snippet(item: dict, index: int = 0, prefix: str = "U") -> dict:
    return {
        "id": str(item.get("id", f"{prefix}-{index + 1:03d}")),
        "section": str(item.get("section", "第一幕")),
        "title": str(item.get("title", "未命名片段")),
        "type": str(item.get("type", "user_note")),
        "content": str(item.get("content", "")),
        "characters": item.get("characters", []) if isinstance(item.get("characters", []), list) else [],
        "tags": item.get("tags", []) if isinstance(item.get("tags", []), list) else [],
        "reveal_from": str(item.get("reveal_from", item.get("section", "第一幕"))),
    }


def get_all_snippets(sources_data: dict) -> list:
    base = []
    if isinstance(sources_data, dict):
        base = sources_data.get("snippets", [])
        if not isinstance(base, list):
            base = []

    normalized_base = [normalize_snippet(item, i, "S") for i, item in enumerate(base)]
    extra = st.session_state.get("extra_snippets", [])

    return normalized_base + extra


def split_text_into_snippets(text: str, section: str, title_prefix: str, tags: list, characters: list) -> list:
    text = text.strip()
    if not text:
        return []

    parts = re.split(r"\n\s*\n", text)
    parts = [p.strip() for p in parts if p.strip()]

    if len(parts) == 1 and len(parts[0]) > 900:
        raw = parts[0]
        parts = [raw[i:i + 600] for i in range(0, len(raw), 600)]

    snippets = []
    timestamp = datetime.now().strftime("%H%M%S")

    for i, part in enumerate(parts):
        snippets.append(
            {
                "id": f"U-{timestamp}-{i + 1:03d}",
                "section": section,
                "title": f"{title_prefix} {i + 1}",
                "type": "uploaded_text",
                "content": part,
                "characters": characters,
                "tags": tags,
                "reveal_from": section,
            }
        )

    return snippets


def get_visible_snippets(all_snippets: list, current_section: str, section_names: list, spoiler_free: bool) -> list:
    visible = []

    for item in all_snippets:
        reveal_from = item.get("reveal_from", item.get("section", "第一幕"))

        if spoiler_free and not section_is_unlocked(reveal_from, current_section, section_names):
            continue

        visible.append(item)

    return visible


def retrieve_snippets(
    all_snippets: list,
    query: str,
    current_section: str,
    section_names: list,
    spoiler_free: bool,
    top_k: int = 5,
) -> list:
    visible = get_visible_snippets(
        all_snippets=all_snippets,
        current_section=current_section,
        section_names=section_names,
        spoiler_free=spoiler_free,
    )

    if not visible:
        return []

    query_text = normalize_text(query)
    query_chars = set(query_text)

    scored = []

    for item in visible:
        score = 0

        content = item.get("content", "")
        title = item.get("title", "")
        section = item.get("section", "")
        tags = item.get("tags", [])
        characters = item.get("characters", [])
        snippet_text = normalize_text(
            f"{item.get('id', '')} {section} {title} {content} {' '.join(tags)} {' '.join(characters)}"
        )

        if section == current_section:
            score += 4

        for tag in tags:
            if tag and tag in query_text:
                score += 8
            if tag and tag in snippet_text:
                score += 1

        for char in characters:
            if char and char in query_text:
                score += 8

        important_terms = [
            "冲突", "主题", "人物", "关系", "潜台词", "台词", "父权", "阶级",
            "繁漪", "周萍", "周朴园", "鲁侍萍", "四凤", "周冲", "鲁大海",
            "旧罪", "毁灭", "体面", "压抑", "反抗", "逃避", "秘密", "真相",
        ]

        for term in important_terms:
            if term in query_text and term in snippet_text:
                score += 4

        if query_text:
            overlap = len(query_chars.intersection(set(snippet_text)))
            score += min(overlap / 8, 8)

        scored.append((score, item))

    scored.sort(key=lambda x: x[0], reverse=True)

    best = [item for score, item in scored if score > 0][:top_k]

    if not best:
        same_section = [item for item in visible if item.get("section") == current_section]
        best = same_section[:top_k] if same_section else visible[:top_k]

    return best


def format_snippets_for_prompt(snippets: list) -> str:
    if not snippets:
        return "暂无检索到的证据片段。"

    parts = []

    for item in snippets:
        parts.append(
            f"""
[{item.get("id", "")}] {item.get("section", "")}｜{item.get("title", "")}
类型：{item.get("type", "")}
相关人物：{safe_join(item.get("characters", []), "、")}
标签：{safe_join(item.get("tags", []), "、")}
内容：{item.get("content", "")}
"""
        )

    return "\n".join(parts)


def display_snippets(snippets: list):
    if not snippets:
        st.write("暂无检索到的证据片段。")
        return

    for item in snippets:
        with st.expander(f"[{item.get('id', '')}] {item.get('section', '')}｜{item.get('title', '')}"):
            st.markdown("**类型**")
            st.write(item.get("type", ""))

            st.markdown("**相关人物**")
            st.write(safe_join(item.get("characters", [])))

            st.markdown("**标签**")
            st.write(safe_join(item.get("tags", [])))

            st.markdown("**片段 / 笔记内容**")
            st.write(item.get("content", ""))


# ============================================================
# Context builders
# ============================================================
def build_section_context(
    sections: dict,
    current_section: str,
    spoiler_free: bool,
    evidence_snippets: list,
) -> str:
    section_names = list(sections.keys())
    current_index = section_names.index(current_section)

    if spoiler_free:
        allowed_sections = section_names[: current_index + 1]
    else:
        allowed_sections = section_names

    context_parts = []

    for name in allowed_sections:
        item = sections[name]

        part = f"""
【{name}】

幕次说明：
{item.get("summary_note", "")}

主要人物：
{safe_join(item.get("characters", []))}

读者目前应知道的信息：
{format_list(item.get("reader_knows", []))}

主要冲突：
{format_list(item.get("conflicts", []))}

相关主题：
{safe_join(item.get("themes", []))}

文本片段 / 笔记：
{item.get("text", "")}
"""
        context_parts.append(part)

    evidence_part = f"""
【检索到的证据片段】
{format_snippets_for_prompt(evidence_snippets)}
"""

    return "\n".join(context_parts) + "\n" + evidence_part


def build_character_context(character_name: str, character_data: dict, current_section: str, evidence_snippets: list) -> str:
    progress_notes = character_data.get("progress_notes", {})

    return f"""
人物：{character_name}

身份：
{character_data.get("identity", "")}

关键词：
{safe_join(character_data.get("keywords", []))}

核心困境：
{character_data.get("core_conflict", "")}

关系网络：
{format_list(character_data.get("relationships", []))}

相关主题：
{safe_join(character_data.get("themes", []))}

当前幕次读者应知道的信息：
{progress_notes.get(current_section, "暂无对应幕次资料")}

检索到的证据片段：
{format_snippets_for_prompt(evidence_snippets)}
"""


def build_dashboard_context(dashboard_data: dict, selected_theme: str = "") -> str:
    conflict_scores = dashboard_data.get("conflict_scores", {})
    themes = dashboard_data.get("themes", {})

    conflict_parts = []

    for section, data in conflict_scores.items():
        conflict_parts.append(
            f"""
【{section}】
冲突强度：{data.get("score", "")}/10
标签：{data.get("label", "")}
说明：{data.get("description", "")}
主要冲突：
{format_list(data.get("main_conflicts", []))}
"""
        )

    if selected_theme and selected_theme in themes:
        theme_data = themes[selected_theme]
        theme_part = f"""
当前选中主题：{selected_theme}
主题说明：{theme_data.get("description", "")}
各幕强度：{theme_data.get("sections", {})}
相关人物：{safe_join(theme_data.get("related_characters", []))}
"""
    else:
        theme_part = "未选择具体主题。"

    return f"""
冲突强度资料：
{"".join(conflict_parts)}

主题资料：
{theme_part}
"""


def build_relationship_dot(
    relationships_data: dict,
    current_section: str,
    section_names: list,
    spoiler_free: bool,
    selected_character: str = "全部人物",
) -> str:
    nodes = relationships_data.get("nodes", {})
    edges = relationships_data.get("edges", [])

    visible_edges = []

    for edge in edges:
        reveal_from = edge.get("reveal_from", "第一幕")

        if spoiler_free and not section_is_unlocked(reveal_from, current_section, section_names):
            continue

        if selected_character != "全部人物":
            if edge.get("source") != selected_character and edge.get("target") != selected_character:
                continue

        visible_edges.append(edge)

    visible_node_names = set()

    for edge in visible_edges:
        visible_node_names.add(edge.get("source"))
        visible_node_names.add(edge.get("target"))

    if selected_character != "全部人物":
        visible_node_names.add(selected_character)

    dot_lines = [
        "graph G {",
        "rankdir=LR;",
        'bgcolor="transparent";',
        'node [shape=box, style="rounded,filled", fillcolor="#F7F7F7", fontname="Microsoft YaHei"];',
        'edge [fontname="Microsoft YaHei", fontsize=10];',
    ]

    for node_name in visible_node_names:
        node_data = nodes.get(node_name, {})
        group = node_data.get("group", "")
        label = f"{node_name}\\n{group}" if group else node_name
        dot_lines.append(f'"{escape_dot(node_name)}" [label="{escape_dot(label)}"];')

    for edge in visible_edges:
        source = edge.get("source", "")
        target = edge.get("target", "")
        relation = edge.get("relation", "")
        dot_lines.append(
            f'"{escape_dot(source)}" -- "{escape_dot(target)}" [label="{escape_dot(relation)}"];'
        )

    dot_lines.append("}")

    return "\n".join(dot_lines)


def build_relationship_context(
    relationships_data: dict,
    current_section: str,
    section_names: list,
    spoiler_free: bool,
    selected_character: str,
    evidence_snippets: list,
) -> str:
    nodes = relationships_data.get("nodes", {})
    edges = relationships_data.get("edges", [])

    visible_edges = []

    for edge in edges:
        reveal_from = edge.get("reveal_from", "第一幕")

        if spoiler_free and not section_is_unlocked(reveal_from, current_section, section_names):
            continue

        if selected_character != "全部人物":
            if edge.get("source") != selected_character and edge.get("target") != selected_character:
                continue

        visible_edges.append(edge)

    edge_text = []

    for edge in visible_edges:
        edge_text.append(
            f"{edge.get('source')} — {edge.get('target')}：{edge.get('relation')}。{edge.get('description', '')}"
        )

    if selected_character != "全部人物":
        character_info = nodes.get(selected_character, {})
        character_text = f"""
当前选中人物：{selected_character}
人物分组：{character_info.get("group", "")}
人物说明：{character_info.get("description", "")}
"""
    else:
        character_text = "当前查看：全部人物关系"

    return f"""
当前阅读进度：{current_section}
不剧透模式：{"开启" if spoiler_free else "关闭"}

{character_text}

当前可见关系：
{format_list(edge_text)}

检索到的证据片段：
{format_snippets_for_prompt(evidence_snippets)}
"""


# ============================================================
# AI call
# ============================================================
def call_chat(system_prompt: str, user_prompt: str, temperature: float = 0.35) -> str:
    if client is None:
        return "你还没有在 .env 文件里填写 OPENAI_API_KEY，所以暂时不能调用 AI。"

    response = client.chat.completions.create(
        model=st.session_state.model_name,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=temperature,
    )

    return response.choices[0].message.content


def ask_reading_ai(context: str, current_section: str, task: str, question: str, spoiler_free: bool) -> str:
    spoiler_rule = (
        "当前开启了不剧透模式：你只能讨论当前幕及之前的信息。"
        if spoiler_free
        else "当前未开启不剧透模式：可以讨论全剧结构，但仍要避免无根据乱编。"
    )

    system_prompt = f"""
你是一个中文现代戏剧互动阅读助手。
你正在帮助用户阅读曹禺《雷雨》。

重要规则：
1. 必须优先依据用户提供的幕次说明、结构化笔记和检索到的证据片段。
2. 不要假装看到了用户没有提供的全文。
3. {spoiler_rule}
4. 如果使用作品整体常识，请明确说“从作品整体常识看”。
5. 关键判断后尽量引用证据片段编号，例如 [S2-01]。
6. 如果材料不足，要直接说明“目前资料不足”，不要硬编。
7. 回答要像可靠的文学阅读助手，不要像死板考试答案。
8. 使用中文回答。
"""

    user_prompt = f"""
当前选择：{current_section}

可用文本、笔记与证据：
{context}

用户选择的功能：
{task}

用户输入的具体需求 / 台词 / 问题：
{question if question.strip() else "用户没有额外输入，请按所选功能进行常规分析。"}

请根据用户选择的功能完成分析，并尽量在关键判断后标出证据片段编号。

如果功能是“本幕摘要”，请包括：
- 本幕发生了什么
- 当前气氛
- 需要注意的人物关系
- 本幕在戏剧推进中的作用

如果功能是“人物关系分析”，请包括：
- 当前涉及人物
- 显性关系
- 潜在权力关系 / 情感压力
- 人物之间的危险点

如果功能是“核心冲突地图”，请包括：
- 主要冲突
- 冲突双方
- 表层原因
- 深层原因
- 冲突强度，1到10分

如果功能是“台词潜台词分析”，请包括：
- 表层意思
- 潜台词
- 说话者心理
- 人物关系 / 权力关系
- 这句台词如何推动戏剧冲突

如果功能是“主题追踪”，请包括：
- 本幕相关主题
- 主题如何通过人物 / 语言 / 情节体现
- 与《雷雨》整体主题的关系

如果功能是“自由提问”，请直接回答用户问题。
"""

    return call_chat(system_prompt, user_prompt)


def ask_character_ai(character_name: str, character_context: str, current_section: str, question: str) -> str:
    system_prompt = """
你是一个中文现代戏剧人物档案助手。
你正在帮助用户理解曹禺《雷雨》中的人物。

回答要求：
1. 优先依据用户提供的人物档案资料和证据片段。
2. 不要假装看到了没有提供的全文。
3. 如果涉及全剧常识，要明确说“从作品整体常识看”。
4. 关键判断后尽量标出证据片段编号，例如 [S3-02]。
5. 使用中文回答。
"""

    user_prompt = f"""
当前人物：{character_name}
当前阅读进度：{current_section}

人物档案与证据资料：
{character_context}

用户问题：
{question if question.strip() else "请根据当前阅读进度，生成这个人物的人物档案分析。"}

请输出：
- 人物当前状态
- 核心困境
- 主要关系网络
- 危险点 / 悲剧因素
- 与主题的关系
- 如果用户有具体问题，请优先回答
"""

    return call_chat(system_prompt, user_prompt)


def ask_dashboard_ai(dashboard_context: str, selected_theme: str, question: str) -> str:
    system_prompt = """
你是一个中文现代戏剧结构分析助手。
你正在帮助用户理解《雷雨》的冲突强度、主题推进和悲剧结构。

回答要求：
1. 必须优先依据用户提供的冲突和主题数据。
2. 可以解释数据背后的戏剧结构意义。
3. 不要假装看到了用户没有提供的全文。
4. 使用中文回答。
"""

    user_prompt = f"""
仪表盘资料：
{dashboard_context}

当前选中主题：
{selected_theme if selected_theme else "未选择具体主题"}

用户问题：
{question if question.strip() else "请解释当前冲突与主题数据说明了什么。"}

请输出：
- 冲突强度如何变化
- 主题如何推进
- 哪些人物最相关
- 这个变化如何服务于悲剧结构
- 如果用户有具体问题，请优先回答
"""

    return call_chat(system_prompt, user_prompt)


def ask_relationship_ai(relationship_context: str, question: str) -> str:
    system_prompt = """
你是一个中文现代戏剧人物关系分析助手。
你正在帮助用户理解曹禺《雷雨》中的人物关系图。

回答要求：
1. 必须优先依据用户提供的人物关系数据和证据片段。
2. 不要假装看到了没有提供的全文。
3. 如果不剧透模式开启，只能基于当前可见关系分析。
4. 关键判断后尽量标出证据片段编号，例如 [S1-02]。
5. 使用中文回答。
"""

    user_prompt = f"""
人物关系资料：
{relationship_context}

用户问题：
{question if question.strip() else "请解释当前人物关系图说明了什么。"}

请输出：
- 当前关系图的核心结构
- 最危险 / 最紧张的关系
- 这些关系如何推动悲剧
- 如果选中了具体人物，请重点解释这个人物在关系网中的位置
- 如果用户有具体问题，请优先回答
"""

    return call_chat(system_prompt, user_prompt)


def ask_source_ai(snippets: list, question: str) -> str:
    system_prompt = """
你是一个中文现代戏剧证据解读助手。
你根据用户检索到的结构化笔记片段回答问题。

回答要求：
1. 必须基于提供的证据片段，不要假装看到了全文。
2. 关键判断后标出片段编号，例如 [S2-03]。
3. 如果证据不足，直接说明不足。
4. 使用中文回答。
"""

    user_prompt = f"""
检索到的证据片段：
{format_snippets_for_prompt(snippets)}

用户问题：
{question if question.strip() else "请解释这些证据片段共同说明了什么。"}

请基于这些证据回答。
"""

    return call_chat(system_prompt, user_prompt)


def add_history(page: str, section: str, task: str, question: str, answer: str):
    st.session_state.analysis_history.insert(
        0,
        {
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "page": page,
            "section": section,
            "task": task,
            "question": question,
            "answer": answer,
        },
    )
    st.session_state.analysis_history = st.session_state.analysis_history[:30]


# ============================================================
# Load data
# ============================================================
init_session_state()

sections = load_json("thunderstorm_sections.json")
characters_data = load_json("thunderstorm_characters.json")
dashboard_data = load_json("thunderstorm_dashboard.json")
relationships_data = load_json("thunderstorm_relationships.json")
sources_data = load_json("thunderstorm_sources.json")

if not sections:
    st.error("没有读取到 thunderstorm_sections.json。请检查文件是否存在。")
    st.stop()

section_names = list(sections.keys())
all_snippets = get_all_snippets(sources_data)


# ============================================================
# App title
# ============================================================
st.title("⛈️ 《雷雨》AI 互动文学档案馆")
st.caption("Thunderstorm Interactive Literary Archive v1.0-local")


# ============================================================
# Sidebar navigation
# ============================================================
with st.sidebar:
    st.header("导航")

    page = st.radio(
        "选择页面",
        [
            "阅读助手",
            "人物档案",
            "人物关系图",
            "冲突&主题面板",
            "证据检索",
            "上传/扩展资料",
            "分析历史/导出",
            "项目说明",
        ],
    )

    st.divider()

    st.header("模型设置")
    st.session_state.model_name = st.text_input(
        "模型名称",
        value=st.session_state.model_name,
        help="默认使用 gpt-4.1-mini。模型名不可用时会报错。",
    )

    st.caption("当前版本：v1.0-local")
    st.caption("本地 Streamlit + OpenAI API")


# ============================================================
# Page 1: Reading Assistant
# ============================================================
if page == "阅读助手":
    with st.sidebar:
        st.header("阅读控制")

        current_section = st.selectbox("选择幕次", section_names)

        spoiler_free = st.checkbox(
            "不剧透模式：只使用当前幕及之前内容",
            value=True,
        )

        task = st.radio(
            "选择功能",
            [
                "本幕摘要",
                "人物关系分析",
                "核心冲突地图",
                "台词潜台词分析",
                "主题追踪",
                "自由提问",
            ],
        )

        question = st.text_area(
            "具体需求 / 台词 / 问题（可选）",
            placeholder=(
                "例如：\n"
                "1. 请重点分析繁漪和周萍的冲突。\n"
                "2. 请把冲突强度解释得更细。\n"
                "3. 请分析这句台词的潜台词。\n"
                "4. 请用适合课堂展示的方式回答。"
            ),
            height=150,
        )

        use_evidence = st.checkbox("自动检索相关证据片段", value=True)
        top_k = st.slider("证据片段数量", min_value=2, max_value=8, value=4)

        run_button = st.button("开始 AI 分析")

    current_data = sections[current_section]
    retrieval_query = (
        f"{current_section} {task} {question} "
        f"{safe_join(current_data.get('characters', []), ' ')} "
        f"{safe_join(current_data.get('themes', []), ' ')}"
    )

    evidence_snippets = (
        retrieve_snippets(
            all_snippets=all_snippets,
            query=retrieval_query,
            current_section=current_section,
            section_names=section_names,
            spoiler_free=spoiler_free,
            top_k=top_k,
        )
        if use_evidence
        else []
    )

    context = build_section_context(
        sections=sections,
        current_section=current_section,
        spoiler_free=spoiler_free,
        evidence_snippets=evidence_snippets,
    )

    col1, col2 = st.columns([1, 1])

    with col1:
        st.subheader(f"原文 / 片段 / 档案：{current_section}")

        st.markdown("### 幕次说明")
        st.write(current_data.get("summary_note", ""))

        st.markdown("### 主要人物")
        st.write(safe_join(current_data.get("characters", [])))

        st.markdown("### 读者目前应知道的信息")
        show_list(current_data.get("reader_knows", []))

        st.markdown("### 主要冲突")
        show_list(current_data.get("conflicts", []))

        st.markdown("### 相关主题")
        st.write(safe_join(current_data.get("themes", [])))

        st.markdown("### 文本片段 / 笔记")
        st.write(current_data.get("text", ""))

        st.markdown("### 自动检索到的证据片段")
        display_snippets(evidence_snippets)

    with col2:
        st.subheader("AI 分析区")

        if run_button:
            with st.spinner("AI 正在分析..."):
                try:
                    answer = ask_reading_ai(
                        context=context,
                        current_section=current_section,
                        task=task,
                        question=question,
                        spoiler_free=spoiler_free,
                    )
                    st.write(answer)
                    add_history("阅读助手", current_section, task, question, answer)

                except Exception as e:
                    st.error(f"出错了：{e}")
                    st.info("常见原因：API key、额度、网络、模型名或 JSON 格式问题。")
        else:
            st.info("请选择左侧功能，可以填写具体需求，然后点击“开始 AI 分析”。")

        if st.session_state.analysis_history:
            st.divider()
            st.markdown("### 最近分析记录")
            for item in st.session_state.analysis_history[:3]:
                with st.expander(f"{item['time']}｜{item['page']}｜{item.get('section', '')}｜{item.get('task', '')}"):
                    if item.get("question"):
                        st.markdown("**你的问题 / 需求：**")
                        st.write(item["question"])
                    st.markdown("**AI 回答：**")
                    st.write(item["answer"])


# ============================================================
# Page 2: Character Archive
# ============================================================
elif page == "人物档案":
    if not characters_data:
        st.error("没有读取到 thunderstorm_characters.json。请先创建这个文件。")
        st.stop()

    with st.sidebar:
        st.header("人物控制")

        current_section = st.selectbox(
            "当前阅读进度",
            section_names,
            key="character_section_select",
        )

        selected_character = st.selectbox(
            "选择人物",
            list(characters_data.keys()),
        )

        character_question = st.text_area(
            "关于这个人物的问题（可选）",
            placeholder=(
                "例如：\n"
                "繁漪到底是反抗者还是破坏者？\n"
                "周朴园的伪善主要体现在哪里？\n"
                "周萍为什么总是在逃避？"
            ),
            height=140,
        )

        character_run_button = st.button("生成人物分析")

    retrieval_query = f"{current_section} {selected_character} {character_question}"

    evidence_snippets = retrieve_snippets(
        all_snippets=all_snippets,
        query=retrieval_query,
        current_section=current_section,
        section_names=section_names,
        spoiler_free=True,
        top_k=5,
    )

    character_data = characters_data[selected_character]
    character_context = build_character_context(
        selected_character,
        character_data,
        current_section,
        evidence_snippets,
    )

    col1, col2 = st.columns([1, 1])

    with col1:
        st.subheader(f"人物档案：{selected_character}")

        st.markdown("### 身份")
        st.write(character_data.get("identity", ""))

        st.markdown("### 关键词")
        st.write(safe_join(character_data.get("keywords", [])))

        st.markdown("### 核心困境")
        st.write(character_data.get("core_conflict", ""))

        st.markdown("### 关系网络")
        show_list(character_data.get("relationships", []))

        st.markdown("### 相关主题")
        st.write(safe_join(character_data.get("themes", [])))

        st.markdown(f"### 当前进度提示：{current_section}")
        progress_notes = character_data.get("progress_notes", {})
        st.write(progress_notes.get(current_section, "暂无对应幕次资料"))

        st.markdown("### 相关证据片段")
        display_snippets(evidence_snippets)

    with col2:
        st.subheader("AI 人物分析区")

        if character_run_button:
            with st.spinner("AI 正在分析人物..."):
                try:
                    answer = ask_character_ai(
                        character_name=selected_character,
                        character_context=character_context,
                        current_section=current_section,
                        question=character_question,
                    )
                    st.write(answer)
                    add_history("人物档案", current_section, selected_character, character_question, answer)

                except Exception as e:
                    st.error(f"出错了：{e}")
                    st.info("常见原因：API key、额度、网络或模型调用问题。")
        else:
            st.info("选择人物和阅读进度后，可以点击“生成人物分析”。")


# ============================================================
# Page 3: Relationship Graph
# ============================================================
elif page == "人物关系图":
    if not relationships_data:
        st.error("没有读取到 thunderstorm_relationships.json。请先创建这个文件。")
        st.stop()

    node_names = list(relationships_data.get("nodes", {}).keys())

    with st.sidebar:
        st.header("关系图控制")

        current_section = st.selectbox(
            "当前阅读进度",
            section_names,
            key="relationship_section_select",
        )

        spoiler_free = st.checkbox(
            "不剧透模式：只显示当前进度已揭示关系",
            value=True,
            key="relationship_spoiler_free",
        )

        selected_character = st.selectbox(
            "聚焦人物",
            ["全部人物"] + node_names,
        )

        relationship_question = st.text_area(
            "关于人物关系的问题（可选）",
            placeholder=(
                "例如：\n"
                "为什么繁漪和周萍的关系这么危险？\n"
                "周朴园在关系网中起什么作用？\n"
                "请解释当前关系图如何推动悲剧。"
            ),
            height=140,
        )

        relationship_run_button = st.button("AI 解读关系图")

    st.subheader("人物关系图")
    st.caption("开启不剧透模式后，关系图只显示当前阅读进度已经揭示的关系。")

    dot = build_relationship_dot(
        relationships_data=relationships_data,
        current_section=current_section,
        section_names=section_names,
        spoiler_free=spoiler_free,
        selected_character=selected_character,
    )

    st.graphviz_chart(dot, use_container_width=True)

    retrieval_query = f"{current_section} {selected_character} {relationship_question}"

    evidence_snippets = retrieve_snippets(
        all_snippets=all_snippets,
        query=retrieval_query,
        current_section=current_section,
        section_names=section_names,
        spoiler_free=spoiler_free,
        top_k=5,
    )

    relationship_context = build_relationship_context(
        relationships_data=relationships_data,
        current_section=current_section,
        section_names=section_names,
        spoiler_free=spoiler_free,
        selected_character=selected_character,
        evidence_snippets=evidence_snippets,
    )

    st.divider()

    col1, col2 = st.columns([1, 1])

    with col1:
        st.subheader("当前可见关系说明")
        st.write(relationship_context)

        st.markdown("### 相关证据片段")
        display_snippets(evidence_snippets)

    with col2:
        st.subheader("AI 关系分析区")

        if relationship_run_button:
            with st.spinner("AI 正在解读人物关系图..."):
                try:
                    answer = ask_relationship_ai(
                        relationship_context=relationship_context,
                        question=relationship_question,
                    )
                    st.write(answer)
                    add_history("人物关系图", current_section, selected_character, relationship_question, answer)

                except Exception as e:
                    st.error(f"出错了：{e}")
                    st.info("常见原因：API key、额度、网络、模型调用问题，或关系数据格式问题。")
        else:
            st.info("可以选择阅读进度和人物，然后点击“AI 解读关系图”。")


# ============================================================
# Page 4: Conflict & Theme Dashboard
# ============================================================
elif page == "冲突&主题面板":
    if not dashboard_data:
        st.error("没有读取到 thunderstorm_dashboard.json。请先创建这个文件。")
        st.stop()

    conflict_scores = dashboard_data.get("conflict_scores", {})
    themes_data = dashboard_data.get("themes", {})

    with st.sidebar:
        st.header("面板控制")

        selected_theme = st.selectbox(
            "选择主题",
            ["总览"] + list(themes_data.keys()),
        )

        dashboard_question = st.text_area(
            "关于冲突 / 主题的问题（可选）",
            placeholder=(
                "例如：\n"
                "为什么第三幕冲突强度这么高？\n"
                "父权主题是怎样一步步推进的？\n"
                "请解释旧罪和毁灭之间的关系。"
            ),
            height=140,
        )

        dashboard_run_button = st.button("AI 解读面板")

    st.subheader("冲突温度计")

    if conflict_scores:
        cols = st.columns(len(conflict_scores))

        for col, (section, data) in zip(cols, conflict_scores.items()):
            score = int(data.get("score", 0))
            with col:
                st.metric(
                    label=section,
                    value=f"{score}/10",
                    delta=data.get("label", ""),
                )
                st.progress(score / 10)
                st.caption(data.get("description", ""))
    else:
        st.write("暂无冲突强度资料。")

    st.divider()

    col1, col2 = st.columns([1, 1])

    with col1:
        st.subheader("各幕冲突详情")

        for section, data in conflict_scores.items():
            with st.expander(f"{section}｜{data.get('label', '')}｜{data.get('score', '')}/10"):
                st.markdown("**说明**")
                st.write(data.get("description", ""))

                st.markdown("**主要冲突**")
                show_list(data.get("main_conflicts", []))

    with col2:
        st.subheader("主题追踪")

        if selected_theme == "总览":
            st.write("选择左侧某个主题，可以查看它在各幕中的强度变化。")

            for theme_name, theme_data in themes_data.items():
                with st.expander(theme_name):
                    st.write(theme_data.get("description", ""))
                    st.markdown("**相关人物**")
                    st.write(safe_join(theme_data.get("related_characters", [])))
        else:
            theme_data = themes_data[selected_theme]
            st.markdown(f"### {selected_theme}")
            st.write(theme_data.get("description", ""))

            st.markdown("**相关人物**")
            st.write(safe_join(theme_data.get("related_characters", [])))

            st.markdown("**各幕主题强度**")
            section_scores = theme_data.get("sections", {})
            for section, score in section_scores.items():
                st.write(f"**{section}：{score}/10｜{score_to_label(score)}**")
                st.progress(score / 10)

    st.divider()
    st.subheader("AI 面板解读")

    if dashboard_run_button:
        with st.spinner("AI 正在解读面板..."):
            try:
                selected_theme_for_ai = "" if selected_theme == "总览" else selected_theme
                dashboard_context = build_dashboard_context(
                    dashboard_data=dashboard_data,
                    selected_theme=selected_theme_for_ai,
                )

                answer = ask_dashboard_ai(
                    dashboard_context=dashboard_context,
                    selected_theme=selected_theme_for_ai,
                    question=dashboard_question,
                )

                st.write(answer)
                add_history("冲突&主题面板", selected_theme, "面板解读", dashboard_question, answer)

            except Exception as e:
                st.error(f"出错了：{e}")
                st.info("常见原因：API key、额度、网络或模型调用问题。")
    else:
        st.info("可以选择主题后点击“AI 解读面板”。")


# ============================================================
# Page 5: Evidence Search
# ============================================================
elif page == "证据检索":
    with st.sidebar:
        st.header("证据检索控制")

        current_section = st.selectbox(
            "当前阅读进度",
            section_names,
            key="source_section_select",
        )

        spoiler_free = st.checkbox(
            "不剧透模式：只检索当前进度已揭示资料",
            value=True,
            key="source_spoiler_free",
        )

        search_query = st.text_area(
            "检索问题 / 关键词",
            placeholder="例如：繁漪 周萍 危险关系；父权；旧罪如何传到下一代",
            height=120,
        )

        top_k = st.slider("返回片段数量", min_value=2, max_value=10, value=6)
        source_run_button = st.button("检索并让 AI 解读")

    st.subheader("证据检索")

    snippets = retrieve_snippets(
        all_snippets=all_snippets,
        query=search_query,
        current_section=current_section,
        section_names=section_names,
        spoiler_free=spoiler_free,
        top_k=top_k,
    )

    col1, col2 = st.columns([1, 1])

    with col1:
        st.markdown("### 检索到的片段")
        display_snippets(snippets)

    with col2:
        st.markdown("### AI 证据解读")

        if source_run_button:
            with st.spinner("AI 正在解读证据..."):
                try:
                    answer = ask_source_ai(snippets, search_query)
                    st.write(answer)
                    add_history("证据检索", current_section, "证据解读", search_query, answer)

                except Exception as e:
                    st.error(f"出错了：{e}")
                    st.info("常见原因：API key、额度、网络或 sources JSON 格式问题。")
        else:
            st.info("输入关键词或问题后，可以点击“检索并让 AI 解读”。")


# ============================================================
# Page 6: Upload / Extend Sources
# ============================================================
elif page == "上传/扩展资料":
    st.subheader("上传 / 扩展资料")

    st.info(
        "这里上传的资料只保存在当前运行会话里。刷新或重启后可能消失。正式长期保存仍建议写入 JSON 文件。"
    )

    upload_type = st.radio(
        "上传类型",
        ["粘贴文本", "上传 TXT", "上传 JSON snippets"],
        horizontal=True,
    )

    col1, col2 = st.columns([1, 1])

    with col1:
        section_for_upload = st.selectbox("这些资料属于哪一幕？", section_names)
        title_prefix = st.text_input("片段标题前缀", value="用户补充片段")

        raw_tags = st.text_input("标签，用逗号分隔", value="补充资料")
        raw_characters = st.text_input("相关人物，用逗号分隔", value="")

        tags = [x.strip() for x in raw_tags.split(",") if x.strip()]
        characters = [x.strip() for x in raw_characters.split(",") if x.strip()]

        if upload_type == "粘贴文本":
            pasted_text = st.text_area(
                "粘贴你的笔记 / 摘录 / 分析材料",
                height=240,
                placeholder="可以粘贴你自己整理的剧情笔记、短摘录、课堂笔记、人物分析等。",
            )

            if st.button("加入资料库"):
                new_snippets = split_text_into_snippets(
                    text=pasted_text,
                    section=section_for_upload,
                    title_prefix=title_prefix,
                    tags=tags,
                    characters=characters,
                )
                st.session_state.extra_snippets.extend(new_snippets)
                st.success(f"已加入 {len(new_snippets)} 个片段。")

        elif upload_type == "上传 TXT":
            uploaded_txt = st.file_uploader("上传 .txt 文件", type=["txt"])

            if uploaded_txt is not None and st.button("读取 TXT 并加入资料库"):
                text = uploaded_txt.read().decode("utf-8", errors="ignore")
                new_snippets = split_text_into_snippets(
                    text=text,
                    section=section_for_upload,
                    title_prefix=title_prefix,
                    tags=tags,
                    characters=characters,
                )
                st.session_state.extra_snippets.extend(new_snippets)
                st.success(f"已加入 {len(new_snippets)} 个片段。")

        elif upload_type == "上传 JSON snippets":
            uploaded_json = st.file_uploader("上传 JSON 文件", type=["json"])

            st.caption(
                "支持格式：{\"snippets\": [...]} 或直接上传 snippets 列表。每个片段最好包含 id, section, title, content, tags, characters。"
            )

            if uploaded_json is not None and st.button("读取 JSON 并加入资料库"):
                try:
                    data = json.loads(uploaded_json.read().decode("utf-8", errors="ignore"))

                    if isinstance(data, dict):
                        raw_snippets = data.get("snippets", [])
                    elif isinstance(data, list):
                        raw_snippets = data
                    else:
                        raw_snippets = []

                    new_snippets = [
                        normalize_snippet(item, i, "UJ")
                        for i, item in enumerate(raw_snippets)
                        if isinstance(item, dict)
                    ]

                    st.session_state.extra_snippets.extend(new_snippets)
                    st.success(f"已加入 {len(new_snippets)} 个 JSON 片段。")

                except Exception as e:
                    st.error(f"读取 JSON 失败：{e}")

    with col2:
        st.markdown("### 当前会话补充片段")
        st.write(f"数量：{len(st.session_state.extra_snippets)}")

        display_snippets(st.session_state.extra_snippets[:10])

        if st.button("清空当前会话补充片段"):
            st.session_state.extra_snippets = []
            st.success("已清空。")
            st.rerun()

        if st.session_state.extra_snippets:
            export_data = json.dumps(
                {"snippets": st.session_state.extra_snippets},
                ensure_ascii=False,
                indent=2,
            )

            st.download_button(
                label="下载当前补充片段 JSON",
                data=export_data,
                file_name="thunderstorm_extra_snippets.json",
                mime="application/json",
            )


# ============================================================
# Page 7: History / Export
# ============================================================
elif page == "分析历史/导出":
    st.subheader("分析历史 / 导出")

    history = st.session_state.analysis_history

    if not history:
        st.info("当前还没有分析历史。你可以先去阅读助手、人物档案或证据检索页面生成一些分析。")
    else:
        st.write(f"当前保存最近 {len(history)} 条分析记录。")

        for i, item in enumerate(history):
            with st.expander(f"{i + 1}. {item['time']}｜{item['page']}｜{item.get('section', '')}｜{item.get('task', '')}"):
                st.markdown("**问题 / 需求**")
                st.write(item.get("question", ""))

                st.markdown("**AI 回答**")
                st.write(item.get("answer", ""))

        export_json = json.dumps(history, ensure_ascii=False, indent=2)

        st.download_button(
            label="下载分析历史 JSON",
            data=export_json,
            file_name="thunderstorm_analysis_history.json",
            mime="application/json",
        )

        export_md_parts = []
        for item in history:
            export_md_parts.append(
                f"""# {item['time']}｜{item['page']}｜{item.get('section', '')}｜{item.get('task', '')}

## 问题 / 需求

{item.get("question", "")}

## AI 回答

{item.get("answer", "")}

---
"""
            )

        export_md = "\n".join(export_md_parts)

        st.download_button(
            label="下载分析历史 Markdown",
            data=export_md,
            file_name="thunderstorm_analysis_history.md",
            mime="text/markdown",
        )

        if st.button("清空分析历史"):
            st.session_state.analysis_history = []
            st.success("已清空分析历史。")
            st.rerun()


# ============================================================
# Page 8: Project Intro
# ============================================================
elif page == "项目说明":
    st.subheader("项目说明")

    st.markdown(
        """
这个项目是一个基于 **Streamlit + OpenAI API** 的《雷雨》互动文学档案馆本地最终原型。

它的目标不是简单总结剧情，而是帮助读者在阅读过程中理解：

- 戏剧结构
- 人物关系
- 冲突推进
- 台词潜台词
- 主题线索
- 阅读进度下的“不剧透”控制
- 基于证据片段的解释与引用
- 自定义补充资料与分析历史导出

当前版本是 **v1.0-local**。
"""
    )

    st.markdown("### 当前功能")

    st.write("- 阅读助手：按幕次生成摘要、人物关系、冲突地图、潜台词分析、主题追踪。")
    st.write("- 人物档案：查看人物身份、关系网络、核心困境和阅读进度提示。")
    st.write("- 人物关系图：可视化展示人物关系，并支持不剧透模式。")
    st.write("- 冲突&主题面板：展示各幕冲突强度与主题推进。")
    st.write("- 证据检索：根据问题检索结构化片段，并让 AI 基于片段回答。")
    st.write("- 上传/扩展资料：支持粘贴文本、上传 TXT、上传 JSON snippets。")
    st.write("- 分析历史/导出：支持导出 JSON 和 Markdown。")

    st.markdown("### 项目结构")

    st.code(
        """
D:\\thunderstorm
├── app.py
├── thunderstorm_sections.json
├── thunderstorm_characters.json
├── thunderstorm_dashboard.json
├── thunderstorm_relationships.json
├── thunderstorm_sources.json
├── requirements.txt
└── .env
""",
        language="text",
    )

    st.markdown("### 到真正公开展示版还差什么")

    st.write("1. 补充更厚的结构化资料：每一幕可以细分为更多场景。")
    st.write("2. 加入更精确的原文片段引用：公开展示时要注意版权，只使用合法文本或短摘录。")
    st.write("3. 整理 README：写清楚项目目标、功能、技术栈和截图。")
    st.write("4. 部署：可以之后部署到 Streamlit Cloud，但 API key 要放在平台 secret 里，不要写进代码。")

    st.markdown("### 使用提醒")

    st.info(
        "如果使用未授权全文，请只用于个人学习和本地测试。公开展示时建议使用你自己整理的结构化笔记、短摘录或公版文本。"
    )
