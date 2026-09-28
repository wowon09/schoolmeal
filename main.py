from collections import defaultdict
from datetime import datetime, timedelta
import re
import pandas as pd
import requests
import streamlit as st
from pytz import timezone


def extract_protein(ntr_info: str) -> float:
    """NTR_INFO 텍스트에서 단백질(g) 수치 추출"""
    if not ntr_info:
        return 0.0
    # '단백질(g) : 31.7' 형태에서 숫자만 추출
    match = re.search(r"단백질\(g\)\s*:\s*([\d.]+)", ntr_info)
    if match:
        return float(match.group(1))
    return 0.0


def fetch_period_meal_info(
    office_code: str, school_code: str, start_date: str, end_date: str
) -> list[dict]:
    """기간 내 급식 목록 가져오기"""
    url = "https://open.neis.go.kr/hub/mealServiceDietInfo"
    params = {
        "Type": "json",
        "ATPT_OFCDC_SC_CODE": office_code,
        "SD_SCHUL_CODE": school_code,
        "MMEAL_SC_CODE": "2",  # 중식
        "MLSV_FROM_YMD": start_date,
        "MLSV_TO_YMD": end_date,
        "pSize": 100,  # 한 번에 받아올 행 수
    }
    try:
        response = requests.get(url, params=params, timeout=10)
        data = response.json()
        if "mealServiceDietInfo" in data:
            return data["mealServiceDietInfo"][1]["row"]
    except Exception:
        return []
    return []


# --- Streamlit UI 연동 부분 ---
# 학교 선택 완료 후 아래 분석 섹션을 추가합니다.

if selected_school:
    st.subheader("📊 요일별 단백질 분석")

    # 지난 60일간의 데이터 분석
    korea_tz = timezone("Asia/Seoul")
    end_dt = datetime.now(korea_tz).date()
    start_dt = end_dt - timedelta(days=60)

    start_str = start_dt.strftime("%Y%m%d")
    end_str = end_dt.strftime("%Y%m%d")

    with st.spinner("최근 급식 영양 정보를 분석 중입니다..."):
        meals = fetch_period_meal_info(
            selected_school["ATPT_OFCDC_SC_CODE"],
            selected_school["SD_SCHUL_CODE"],
            start_str,
            end_str,
        )

    if meals:
        weekday_map = {0: "월요일", 1: "화요일", 2: "수요일", 3: "목요일", 4: "금요일"}
        protein_by_day = defaultdict(list)

        for meal in meals:
            ymd = meal.get("MLSV_YMD")
            ntr_info = meal.get("NTR_INFO", "")

            if ymd:
                dt = datetime.strptime(ymd, "%Y%m%d")
                weekday = dt.weekday()
                if weekday < 5:  # 월~금요일만 포함
                    protein = extract_protein(ntr_info)
                    if protein > 0:
                        protein_by_day[weekday_map[weekday]].append(protein)

        # 요일별 평균 계산
        avg_protein = {}
        for day in ["월요일", "화요일", "수요일", "목요일", "금요일"]:
            values = protein_by_day.get(day, [])
            avg_protein[day] = round(sum(values) / len(values), 2) if values else 0.0

        df_protein = pd.DataFrame(
            list(avg_protein.items()), columns=["요일", "평균 단백질(g)"]
        )

        # 가장 단백질이 높은 요일 찾기
        max_day = df_protein.loc[df_protein["평균 단백질(g)"].idxmax()]

        # 결과 출력
        st.success(
            f"💡 최근 두 달간 분석 결과, 단백질이 가장 많은 요일은 **{max_day['요일']}** (평균 {max_day['평균 단백질(g)']}g) 입니다!"
        )

        # 막대 그래프로 시각화
        st.bar_chart(data=df_protein.set_index("요일"))
    else:
        st.info("분석할 급식 데이터가 충분하지 않습니다.")
