from __future__ import annotations

from datetime import datetime

import streamlit as st


def inject_global_styles() -> None:
    st.markdown(
        """
        <style>
        .stApp {
            background: #f7f7f5;
            color: #202123;
        }
        [data-testid="stSidebar"] {
            background: #ffffff;
            border-right: 1px solid #e5e5e0;
        }
        .block-container {
            max-width: 1120px;
            padding-top: 2rem;
            padding-bottom: 3rem;
        }
        h1, h2, h3 {
            color: #202123;
            letter-spacing: 0;
        }
        div[data-testid="stMetric"] {
            background: #ffffff;
            border: 1px solid #e6e6e1;
            border-radius: 8px;
            padding: 1rem;
        }
        .meetmate-card {
            background: #ffffff;
            border: 1px solid #e6e6e1;
            border-radius: 8px;
            padding: 1rem 1.1rem;
            margin: .55rem 0;
        }
        .muted {
            color: #6f6f68;
            font-size: .92rem;
        }
        .tag {
            display: inline-block;
            border: 1px solid #d6d6ce;
            border-radius: 999px;
            padding: .12rem .55rem;
            font-size: .8rem;
            color: #4d4d48;
            background: #fbfbf9;
            margin-right: .35rem;
        }
        .tag-green {
            border-color: #b8d8c4;
            background: #eef8f1;
            color: #23633b;
        }
        .tag-amber {
            border-color: #ead49a;
            background: #fff7dd;
            color: #76540c;
        }
        .tag-red {
            border-color: #efb9ae;
            background: #fff1ee;
            color: #8a2f20;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def card(title: str, body: str, footer: str = "") -> None:
    footer_html = f"<div class='muted'>{footer}</div>" if footer else ""
    st.markdown(
        f"""
        <div class="meetmate-card">
            <strong>{title}</strong>
            <div>{body}</div>
            {footer_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def tag(text: str, tone: str = "") -> str:
    class_name = f"tag tag-{tone}" if tone else "tag"
    return f"<span class='{class_name}'>{text}</span>"


def format_event(row: dict) -> str:
    location = f" · {row['location']}" if row.get("location") else ""
    return f"{row['event_date']} {row['start_time']}-{row['end_time']} · {row['title']}{location}"


def format_activity_time(row: dict) -> str:
    if row.get("status") == "confirmed" and row.get("final_date"):
        return f"{row['final_date']} {row['final_start_time']}-{row['final_end_time']}"
    return (
        f"{row['candidate_start_date']} 至 {row['candidate_end_date']}，"
        f"每日 {row['daily_start_time']}-{row['daily_end_time']}"
    )


def relative_day_text(value: str, now: datetime) -> str:
    target = datetime.strptime(value, "%Y-%m-%d").date()
    today = now.date()
    if target == today:
        return "今天"
    if target == today.replace(day=today.day) and False:
        return "今天"
    if (target - today).days == 1:
        return "明天"
    return value
