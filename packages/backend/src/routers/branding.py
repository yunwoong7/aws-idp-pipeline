import json
import os
from pathlib import Path
from typing import Dict, Any

from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import JSONResponse

router = APIRouter()

# 설정 파일 경로
CONFIG_FILE = Path(__file__).parent.parent.parent / "config" / "branding.json"
FRONTEND_PUBLIC_DIR = Path(__file__).parent.parent.parent.parent / "frontend" / "public"
USER_LOGO_PATH = FRONTEND_PUBLIC_DIR / "user_logo.png"


def load_branding_config() -> Dict[str, Any]:
    """브랜딩 설정 파일을 로드합니다."""
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        # 기본 설정 반환
        return {
            "default": {
                "companyName": "AWS IDC",
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
            
            # public 디렉토리 생성
            os.makedirs(FRONTEND_PUBLIC_DIR, exist_ok=True)
            
            # 파일 저장
            with open(USER_LOGO_PATH, "wb") as buffer:
                content = await logoFile.read()
                buffer.write(content)
            
            config["user"]["logoUrl"] = "/user_logo.png"
        
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