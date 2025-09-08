import json
import os
from pathlib import Path
from typing import Dict, Any

from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import JSONResponse, FileResponse

router = APIRouter()

# 설정/저장 경로 (backend 루트)
# __file__ = packages/backend/src/routers/branding.py -> parent: routers -> parent: src -> parent: backend
BASE_DIR = Path(__file__).resolve().parent.parent  # .../packages/backend
CONFIG_FILE = BASE_DIR / "config" / "branding.json"

# 프론트엔드 public 디렉터리는 컨테이너(ECS) 환경에 없을 수 있으므로
# 백엔드 전용 디렉터리에 사용자 로고를 저장하고 API로 서빙합니다.
BACKEND_BRANDING_DIR = BASE_DIR / "data" / "branding"
USER_LOGO_PATH = BACKEND_BRANDING_DIR / "user_logo.png"
VERSION_FILE = Path(__file__).resolve().parent.parent.parent / "__version__"


def load_branding_config() -> Dict[str, Any]:
    """브랜딩 설정 파일을 로드합니다."""
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        # 기본 설정 반환
        return {
            "default": {
                "companyName": "AWS IDP",
                "logoUrl": "/default_logo.png",
                "description": "Transform Documents into\nActionable Insights"
            },
            "user": {
                "companyName": "",
                "logoUrl": "",
                "description": ""
            }
        }


def save_branding_config(config: Dict[str, Any]) -> None:
    """브랜딩 설정 파일을 저장합니다."""
    os.makedirs(CONFIG_FILE.parent, exist_ok=True)
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


def load_version() -> str:
    """버전 파일에서 버전을 읽어옵니다. 기본값은 '0.1.0'."""
    try:
        print(VERSION_FILE.exists())
        if VERSION_FILE.exists():
            print(VERSION_FILE.read_text(encoding="utf-8").strip())
            return VERSION_FILE.read_text(encoding="utf-8").strip() or "0.1.0"
    except Exception:
        pass
    return "0.1.0"


def get_effective_settings(config: Dict[str, Any]) -> Dict[str, str]:
    """user 설정이 있으면 user를, 없으면 default를 반환합니다."""
    default_settings = config.get("default", {})
    user_settings = config.get("user", {})
    
    effective_settings = {}
    for key in ["companyName", "logoUrl", "description"]:
        if user_settings.get(key):
            effective_settings[key] = user_settings[key]
        else:
            effective_settings[key] = default_settings.get(key, "")
    
    # 사용자 로고 파일이 실제로 존재하면 API 경로를 사용하도록 강제
    if USER_LOGO_PATH.exists():
        effective_settings["logoUrl"] = "/api/branding/logo"
    else:
        # 과거 저장값("/user_logo.png")을 사용하는 경우에도 API 경로로 정규화
        if effective_settings.get("logoUrl", "").endswith("/user_logo.png"):
            effective_settings["logoUrl"] = "/api/branding/logo"
        # 파일이 없는데 사용자 설정이 API 경로를 가리키는 경우 기본 로고로 폴백
        elif effective_settings.get("logoUrl", "").startswith("/api/branding/logo"):
            effective_settings["logoUrl"] = default_settings.get("logoUrl", "/default_logo.png")
    # 버전 포함
    effective_settings["version"] = load_version()
    return effective_settings


@router.get("/settings")
async def get_branding_settings():
    """브랜딩 설정을 조회합니다."""
    try:
        config = load_branding_config()
        effective_settings = get_effective_settings(config)

        return JSONResponse(content={
            "success": True,
            "data": effective_settings
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"설정을 불러오는 중 오류가 발생했습니다: {str(e)}")


@router.post("/settings")
async def save_branding_settings(
    companyName: str = Form(...),
    description: str = Form(...),
    logoFile: UploadFile = File(None)
):
    """브랜딩 설정을 저장합니다."""
    try:
        config = load_branding_config()
        
        # 사용자 설정 업데이트
        config["user"]["companyName"] = companyName
        config["user"]["description"] = description
        
        # 로고 파일 처리
        if logoFile and logoFile.filename:
            # 이미지 파일 검증
            if not logoFile.content_type or not logoFile.content_type.startswith("image/"):
                raise HTTPException(status_code=400, detail="이미지 파일만 업로드 가능합니다.")

            # 저장 디렉토리 생성
            os.makedirs(BACKEND_BRANDING_DIR, exist_ok=True)

            # 파일 저장
            with open(USER_LOGO_PATH, "wb") as buffer:
                content = await logoFile.read()
                buffer.write(content)

            # 프론트 경로가 아닌 백엔드 API 경로로 설정
            config["user"]["logoUrl"] = "/api/branding/logo"
        
        # 설정 파일 저장
        save_branding_config(config)
        
        return JSONResponse(content={
            "success": True,
            "message": "설정이 성공적으로 저장되었습니다."
        })
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"설정을 저장하는 중 오류가 발생했습니다: {str(e)}")


@router.delete("/settings")
async def reset_branding_settings():
    """브랜딩 설정을 초기화합니다."""
    try:
        config = load_branding_config()
        
        # 사용자 업로드 로고 삭제
        if USER_LOGO_PATH.exists():
            USER_LOGO_PATH.unlink()
        
        # 사용자 설정 초기화
        config["user"] = {
            "companyName": "",
            "logoUrl": "",
            "description": ""
        }
        
        # 설정 파일 저장
        save_branding_config(config)
        
        return JSONResponse(content={
            "success": True,
            "message": "설정이 기본값으로 초기화되었습니다."
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"설정을 초기화하는 중 오류가 발생했습니다: {str(e)}")


@router.get("/logo")
async def get_user_logo():
    """사용자 업로드 로고 파일을 서빙합니다. 파일이 없으면 404를 반환합니다."""
    try:
        if USER_LOGO_PATH.exists():
            return FileResponse(path=str(USER_LOGO_PATH), media_type="image/png")
        # 파일이 없으면 404. 프론트에서 onError로 기본 로고로 대체합니다.
        raise HTTPException(status_code=404, detail="User logo not found")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"로고를 불러오는 중 오류가 발생했습니다: {str(e)}")