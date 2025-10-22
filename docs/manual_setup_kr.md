<h2 align="center">로컬 배포 가이드 (Kor)</h2>

이 가이드는 개발 환경을 로컬에서 설정하기 위한 것입니다. 로컬 배포 시 필요한 도구와 종속성을 직접 설치해야 합니다. **5단계**까지 진행하면 완전한 로컬 개발 환경이 구축되며, 선택 사항인 **6단계**에서는 전체 애플리케이션을 AWS ECS에 배포해 외부에서 접근할 수 있는 실행 환경을 만드는 방법을 설명합니다.

---

## 사전 준비 사항

시작하기 전에, **로컬 머신**에 다음 소프트웨어와 설정이 준비되어 있는지 확인하세요.

1.  **필수 도구**
    * [**Python**](https://www.python.org/) (3.12+)
    
    * [**Node.js**](https://nodejs.org/ko/download) (20+)
    
    * [**pnpm**](https://pnpm.io/installation)
    
    * **uv**: Python 설치 후, 다음 명령어 실행

      ```bash
      pip install uv
      ```
    
    * [**AWS CLI**](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html)
    
    * [**AWS CDK**](https://docs.aws.amazon.com/cdk/v2/guide/getting-started.html)
    
    *   **jq**
    
2.  **AWS 자격 증명**
    * 로컬 머신에 [AWS CLI가 설치](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html)되고 구성되어 있어야 합니다. 다음 명령어로 프로필을 생성할 수 있습니다.
    
      ```bash
      aws configure --profile your-profile-name
      ```
    * `~/.aws/credentials`와 `~/.aws/config` 파일에 이름 있는 프로필이 설정되어 있어야 합니다. Devcontainer는 이 디렉터리를 자동으로 마운트하여 컨테이너 내에서 프로필을 사용할 수 있게 합니다.

---

## 설정 과정

### 1단계: 설치 및 확인

필수 도구 설치 명령어는 운영체제에 따라 다릅니다. 설치 후, 다음 명령어를 실행하여 모든 것이 정상 작동하는지 확인하세요:

```bash
aws --version
node --version
pnpm --version
python3 --version
uv --version
cdk --version
jq --version
```

### 2단계: 프로젝트 의존성 설치

**프로젝트 루트 디렉터리에서** 다음 명령어를 실행하여 의존성을 설치하세요.

```bash
# Python 가상 환경 생성
uv venv

# 가상 환경 활성화 (쉘에 따라 명령어가 다릅니다)
# macOS/Linux: `source .venv/bin/activate`
# Windows: `.venv\Scripts\activate.bat`
source .venv/bin/activate

# Python 의존성 설치
uv sync

# Node.js 의존성 설치
pnpm install
```

### 3단계: AWS 인프라 배포

이 단계에서는 핵심 클라우드 리소스를 프로비저닝합니다. 활성화된 Python 가상 환경 내에서 실행해야 합니다.

1.  인프라 패키지로 이동:
    ```bash
    cd packages/infra
    ```
2.  AWS 프로필을 사용하여 배포 스크립트 실행:
    ```bash
    ./deploy-infra.sh your-aws-profile-name
    ```

> **배포 소요 시간 및 확인**
>
> *   배포에는 **40~60분**이 소요될 수 있습니다.
> *   **배포가 성공적으로 완료되면** AWS OpenSearch 콘솔로 이동하여 `nori` (한국어 형태소 분석기) 플러그인이 도메인에 올바르게 설치되었는지 확인하세요. 플러그인 패키지 설치에는 추가로 **10~20분** 정도 소요될 수 있습니다.

### 4단계: 애플리케이션 로컬 실행

두 개의 별도 터미널이 필요합니다. 백엔드를 실행하는 새 터미널에서도 가상 환경을 활성화해야 합니다.

**터미널 1: 백엔드 시작**

```bash
# 필요 시 가상 환경 활성화. Windows에서는 `.venv\Scripts\activate.bat` 사용

# 백엔드 서버 시작
python packages/backend/main.py
```

**터미널 2: 프론트엔드 시작**

```bash
# 프론트엔드 개발 서버 시작
pnpm dev
```

### 5단계: 로컬 애플리케이션 접속

두 서버가 모두 실행 중일 때, 브라우저에서 **[http://localhost:3000](http://localhost:3000)** 으로 접속하세요.

---

### 6단계 (선택 사항): AWS ECS에 배포

이 단계는 AWS ECS와 Application Load Balancer (ALB)를 사용하여 애플리케이션을 외부에서 접근 가능한 환경에 배포하는 방법입니다. 다른 사람과 공유하거나 스테이징 환경을 만들 때 유용합니다.

**1. 애플리케이션 접근**

사용자는 Frontend URL을 통해 애플리케이션에 접속할 수 있으며, `AdminUsername`과 `TemporaryPassword`를 사용하여 로그인할 수 있습니다.  
최초 로그인 시에는 임시 비밀번호를 반드시 변경해야 합니다.

**2. 서비스 배포**

터미널에서 서비스 배포 스크립트를 실행하세요.

```bash
# 아직 인프라 패키지에 있지 않다면 이동
cd packages/infra

# AWS 프로필을 사용하여 서비스 배포 스크립트 실행
./deploy-services.sh your-aws-profile-name
```

**3. 배포된 애플리케이션 접속**

* 스크립트 완료 후, 프론트엔드의 공개 URL이 출력됩니다.

  ```
  Service URLs:
    Frontend:    http://your-alb-dns-name.amazonaws.com
  ```

* 프로젝트 루트의 자동 생성된 `.env` 파일 내 `FRONTEND_URL` 키에서도 이 URL을 확인할 수 있습니다.

* 출력된 URL을 브라우저에서 열어 접속하세요. IP가 변경되면 `.toml` 파일에 새 IP를 추가하고 `./deploy-services.sh` 스크립트를 다시 실행해야 합니다.

---

**배포 완료!** 이제 로컬 실행 또는 ECS 환경에서 AWS IDP를 테스트할 수 있습니다.

