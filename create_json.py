
import os
import requests
from bs4 import BeautifulSoup
from pdf2image import convert_from_path
from datetime import datetime, timedelta
import pdfplumber
import json
import re
from github import Github
from github.GithubException import UnknownObjectException

# 설정
BASE_URL = "https://assembly.go.kr/portal/bbs/B0000054/list.do?pageIndex=1&menuNo=600100&sdate=&edate=&searchDtGbn=c0&pageUnit=10&pageIndex=1&cl1Cd=AN01"
PDF_PATH = "weekly_menu.pdf"  # PDF 파일 경로
OUTPUT_PATH = "weekly_menu.json"  # 저장할 JSON 파일 경로

# 식당별 열 인덱스 정의 (0-based index)
restaurant_columns = {
    "본관1식당": 1,
    "회관1식당": 4,
    "도서관식당": 9,
    "박물관식당": 10,
}

# 요일별 기준 행 인덱스 정의
weekday_rows = {
    "월요일": 3,
    "화요일": 6,
    "수요일": 9,
    "목요일": 12,
    "금요일": 15,
    "토요일": 18,
    "일요일": 19,
}

def find_latest_pdf_url():
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }

    ### 운영시 verify=False 삭제
    response = requests.get(BASE_URL, headers=headers)
    soup = BeautifulSoup(response.text, "html.parser")

    # 날짜 계산: 수집일 기준 4일 전부터 당일까지
    today = datetime.now()
    four_days_ago = today - timedelta(days=4)
    print(f"오늘: {today}, 4일 전: {four_days_ago}")

    # 게시물 리스트 파싱 (제목, 작성일, 다운로드 컬럼 추출)
    div_container = soup.find("div", class_="board01 pr td_center board-added")
    if not div_container:
        print("! 게시판 컨테이너를 찾을 수 없습니다. 구조 변경 여부 확인 필요")
        return None
    tbody = div_container.find("tbody")
    if not tbody:
        print("! tbody를 찾을 수 없습니다. HTML 구조 변경 여부 확인 필요")
        return None
    rows = tbody.find_all("tr") if tbody else []

    for row in rows:
        columns = row.find_all("td")   # <td> 태그로 열 가져오기
        if len(columns) >= 7:   # 다운로드 열 포함 최소 7개 확인
            title = columns[2].find("a").text.strip()   # 제목 컬럼에서 <a> 태그의 텍스트 추출
            date_text = columns[4].text.strip()   # 작성일 컬럼
            download_column = columns[6]  # 다운로드 컬럼

            # 날짜 확인
            try:
                post_date = datetime.strptime(date_text, "%Y-%m-%d")
                print(f"게시물 날짜 파싱 성공: {post_date}")
                if four_days_ago <= post_date <= today and "주간식단표" in title:
                    # onclick 속성 찾기
                    link = download_column.find("a", onclick=True)
                    print(f"Title: {title}, Date: {date_text}, Download Link Tag: {link}")
                    
                    if link:
                        onclick_content = link["onclick"]
                        print(f"onclick content: {onclick_content}")

                        # gfn_atchFileDownload 함수 파싱
                        match = re.search(r"gfn_atchFileDownload\('([^']*)', '([^']*)', '([^']*)', '([^']*)'\)", onclick_content)
                        if match:
                            portal, menu_no, file_id, file_sn = match.groups()

                            # URL 구성
                            base_url = "https://assembly.go.kr"
                            pdf_url = f"{base_url}/portal/cmmn/file/fileDown.do?menuNo={menu_no}&atchFileId={file_id}&fileSn={file_sn}&historyBackUrl=https%3A%2F%2Fassembly.go.kr%2Fportal%2Fbbs%2FB0000054%2Flist.do%3FpageIndex%3D1%26menuNo%3D600100%26sdate%3D%26edate%3D%26searchDtGbn%3Dc0%26pageUnit%3D10%26pageIndex%3D1%26cl1Cd%3DAN01"
                            print(f"PDF URL: {pdf_url}")
                            return pdf_url
                    
            except ValueError:
                continue
    return None

def download_pdf(pdf_url):
    """PDF 파일 다운로드"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Referer": BASE_URL  # 요청 출처를 명시
    }
    response = requests.get(pdf_url, headers=headers, stream=True)
    if response.status_code == 200:
        with open(PDF_PATH, "wb") as pdf_file:
          pdf_file.write(response.content)
        print(f"PDF 다운로드 완료: {PDF_PATH}")
    else:
        print(f"PDF 다운로드 실패: {response.status_code}")

def convert_pdf_to_jpg():
    """PDF를 JPG로 변환"""
    images = convert_from_path(PDF_SAVE_PATH)
    if images:
        images[0].save(JPG_SAVE_PATH, "JPEG")   # 첫 페이지를 JPG로 저장

def upload_to_github(file_path, repo_name="gyo-lab/weeklymenu", branch="main"):
    """GitHub에 파일 업로드"""
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise ValueError("GITHUB_TOKEN 환경 변수가 설정되지 않았습니다.")

    g = Github(token)
    repo = g.get_repo(repo_name)

    with open(file_path, "rb") as file:
        content = file.read()
        
    file_name = os.path.basename(file_path)
    print(f"업로드할 파일 이름: {file_name}")
    try:
        # 기존 파일 확인
        existing_file = repo.get_contents(file_name, ref=branch)
        print(f"기존 파일 발견: {existing_file.path}, 파일 업데이트 중...")
        # 기존 파일 업데이트
        repo.update_file(existing_file.path, "Update weekly menu", content, existing_file.sha, branch=branch)
        print(f"파일 업데이트 완료: {file_name}")
    except UnknownObjectException:
        print("기존 파일이 없습니다. 새로 생성 중...")
        # 파일이 없는 경우 새로 생성
        repo.create_file(file_name, "Add weekly menu", content, branch=branch)
        print(f"새 파일 생성 완료: {file_name}")
    except Exception as e:
        print(f"파일 업로드 중 오류 발생: {e}")

def clean_menu_text(text):
    """메뉴 텍스트 전처리: 줄바꿈 → 쉼표, 공백 정리, kcal 괄호 처리"""
    if not text:
        return ""

    # 줄바꿈을 쉼표로 변경하고 항목별로 분리
    items = re.split(r'[\n/]', text.strip())
    cleaned_items = []
    kcal_part = ""

    for item in items:
        item_no_space = re.sub(r'\s+', '', item)
        # kcal 항목 따로 분리
        if "kcal" in item_no_space:
            kcal_part = f"({item_no_space})"
        else:
            cleaned_items.append(item_no_space)

    return ", ".join(cleaned_items) + (f" {kcal_part}" if kcal_part else "")

def parse_pdf_to_json(pdf_path: str, output_path: str):
    with pdfplumber.open(pdf_path) as pdf:
        table = pdf.pages[0].extract_table()  # 첫 페이지에서 표 데이터 추출
        menu_data = {}  # 최종 JSON 데이터를 담을 딕셔너리

        for weekday, base_row in weekday_rows.items():
            menu_data[weekday] = {}  # 각 요일별 데이터 초기화

            for restaurant, col_index in restaurant_columns.items():
                menu_data[weekday][restaurant] = {}  # 식당별 데이터 초기화

                try:
                    # 토요일, 일요일은 점심만 제공됨
                    if weekday in ["토요일", "일요일"]:
                        lunch_cell = table[base_row][col_index] if base_row < len(table) else ""
                        menu_data[weekday][restaurant]["아침"] = ""
                        menu_data[weekday][restaurant]["점심"] = clean_menu_text(lunch_cell)
                        menu_data[weekday][restaurant]["저녁"] = ""

                    # 도서관식당, 박물관식당은 아침 없음
                    elif restaurant in ["도서관식당", "박물관식당"]:
                        lunch_cell = table[base_row][col_index] if base_row < len(table) else ""
                        dinner_cell = table[base_row + 2][col_index] if base_row + 2 < len(table) else ""
                        menu_data[weekday][restaurant]["아침"] = ""
                        menu_data[weekday][restaurant]["점심"] = clean_menu_text(lunch_cell)
                        menu_data[weekday][restaurant]["저녁"] = clean_menu_text(dinner_cell)

                    # 일반 식당: 아침, 점심, 저녁 제공
                    else:
                        breakfast_cell = table[base_row][col_index] if base_row < len(table) else ""
                        lunch_cell = table[base_row + 1][col_index] if base_row + 1 < len(table) else ""
                        dinner_cell = table[base_row + 2][col_index] if base_row + 2 < len(table) else ""
                        menu_data[weekday][restaurant]["아침"] = clean_menu_text(breakfast_cell)
                        menu_data[weekday][restaurant]["점심"] = clean_menu_text(lunch_cell)
                        menu_data[weekday][restaurant]["저녁"] = clean_menu_text(dinner_cell)

                except Exception as e:
                    print(f"Error parsing {weekday} - {restaurant}: {e}")
                    menu_data[weekday][restaurant] = {"아침": "", "점심": "", "저녁": ""}

    # JSON 파일로 저장
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(menu_data, f, ensure_ascii=False, indent=2)
    print(f"JSON 저장 완료: {output_path}")

def main():
    """전체 프로세스 실행"""
    pdf_url = find_latest_pdf_url()
    if pdf_url:
        print(f"최신 PDF URL: {pdf_url}")
        download_pdf(pdf_url)
        convert_pdf_to_jpg()
        upload_to_github(JPG_SAVE_PATH)
        parse_pdf_to_json(PDF_PATH, OUTPUT_PATH)
    else:
        print("최신 게시물을 찾을 수 없습니다.")

if __name__ == "__main__":
    main()