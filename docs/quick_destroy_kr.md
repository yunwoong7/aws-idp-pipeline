<h2 align="center">CloudShell & CodeBuild 인프라 삭제 가이드 (Kor)</h2>

이 문서는 AWS CloudShell과 CodeBuild를 활용하여 배포된 AWS IDP 인프라를 안전하게 삭제하는 방법을 안내합니다.

## 사전 준비 사항

- CloudShell 실행 권한이 있어야 합니다.
- CodeBuild 프로젝트에 접근할 수 있는 권한이 필요합니다.
- 배포했던 동일한 AWS 리전을 선택해야 합니다.

## 삭제 단계

1. CloudShell을 실행합니다.

2. 소스 코드를 가져옵니다. 이미 클론되어 있다면 이 단계는 생략할 수 있지만, 새로운 CloudShell을 실행하는 경우 아래 명령어를 다시 실행해야 합니다.
   ```
   git clone https://github.com/your-repo/aws-idp-pipeline.git
   cd aws-idp-pipeline
   ```

3. 삭제 스크립트 파일(`cleanup.sh`)을 실행합니다.

4. <div align="center">   
     <img src="assets/quick-destroy-1.png" alt="quick-destroy-1" width="900"/>
   </div>

   ```
   chmod +x cleanup.sh && ./cleanup.sh
   ```
   만약 CloudShell을 사용하지 않는 경우, 로컬 환경에서 `/Users/yunwoong/PrototypingProjects/aws-idp-pipeline/packages/infra/cleanup.sh` 스크립트를 실행할 수 있습니다.
   ```
   chmod +x packages/infra/cleanup.sh && ./packages/infra/cleanup.sh
   ```

## 삭제 모니터링

- AWS CodeBuild 콘솔에서 삭제 진행 상황을 확인할 수 있습니다.
- 삭제가 오래 걸리거나 타임아웃으로 실패하는 경우가 있는데, 이때는 CodeBuild에서 "빌드 재시도" 버튼을 눌러 삭제 과정을 다시 시작할 수 있습니다.

<div align="center">   
<img src="assets/quick-destroy-3.png" alt="quick-destroy-2" width="900"/>
</div>

## 삭제 완료 후

- CodeBuild 로그에서 삭제 완료 메시지를 확인합니다.

- S3 버킷, DynamoDB 테이블, OpenSearch, Lambda, Step Functions 등 주요 리소스가 정상적으로 제거되었는지 확인합니다.

- 일반적으로 삭제가 성공하지만, 경우에 따라 리소스가 삭제되지 않는 경우가 있으므로, 이 경우 CloudFormation 콘솔에 접속하여 남아있는 스택을 수동으로 삭제하시기 바랍니다.


<div align="center">   
<img src="assets/quick-destroy-2.png" alt="quick-destroy-2" width="900"/>
</div>
