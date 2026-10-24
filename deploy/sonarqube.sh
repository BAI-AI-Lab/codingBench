#!/bin/bash
# Local SonarQube for `cb quality --sonar` (the static-quality protocol of arXiv:2610.19167 uses SonarQube 10.4). As root.
#   deploy/sonarqube.sh start   # container cb-sonarqube on 127.0.0.1:9000 (data in $DIR), scanner unpacked, token in $ENV
#   deploy/sonarqube.sh stop    # remove the container; data and token stay, so the next start reuses them
# Then:  set -a; source /root/.config/code_bench/sonar.env; set +a; cb quality <run dir> --sonar
set -euo pipefail
DIR=${SONAR_DIR:-/data/hx/sonarqube}
IMAGE=sonarqube:10.4-community
NAME=cb-sonarqube
URL=http://127.0.0.1:9000
ENV=/root/.config/code_bench/sonar.env
SCANNER=sonar-scanner-cli-5.0.1.3006-linux
case "${1:-}" in
start)
  mkdir -p "$DIR"/data "$DIR"/logs "$DIR"/extensions
  chown -R 1000:1000 "$DIR"/data "$DIR"/logs "$DIR"/extensions   # the image runs as uid 1000
  # bootstrap checks off: Elasticsearch would otherwise need vm.max_map_count raised on this shared host
  docker inspect $NAME >/dev/null 2>&1 || docker run -d --name $NAME -p 127.0.0.1:9000:9000 \
    -e SONAR_ES_BOOTSTRAP_CHECKS_DISABLE=true -v "$DIR"/data:/opt/sonarqube/data -v "$DIR"/logs:/opt/sonarqube/logs \
    -v "$DIR"/extensions:/opt/sonarqube/extensions $IMAGE >/dev/null
  docker start $NAME >/dev/null
  until curl -sf $URL/api/system/status | grep -q '"status":"UP"'; do sleep 5; done
  if [ ! -x "$DIR"/sonar-scanner/bin/sonar-scanner ]; then
    [ -s "$DIR"/scanner.zip ] || curl -sSL -o "$DIR"/scanner.zip https://binaries.sonarsource.com/Distribution/sonar-scanner-cli/$SCANNER.zip
    rm -rf "$DIR"/sonar-scanner "$DIR"/sonar-scanner-5.0.1.3006-linux
    unzip -q "$DIR"/scanner.zip -d "$DIR" && mv "$DIR"/sonar-scanner-5.0.1.3006-linux "$DIR"/sonar-scanner
    chmod -R a+rX "$DIR"/sonar-scanner
  fi
  if [ ! -s $ENV ]; then   # first start: replace the default admin password, make a token for cb
    pass="Cb-$(openssl rand -hex 12)-Aa1!"
    curl -sf -u admin:admin -X POST $URL/api/users/change_password -d login=admin -d previousPassword=admin \
      --data-urlencode "password=$pass"
    token=$(curl -sf -u "admin:$pass" -X POST $URL/api/user_tokens/generate -d name=codingbench |
            python3 -c 'import json, sys; print(json.load(sys.stdin)["token"])')
    (umask 077; mkdir -p "$(dirname $ENV)"
     printf 'SONAR_URL=%s\nSONAR_TOKEN=%s\nSONAR_SCANNER=%s\nSONAR_ADMIN_PASSWORD=%s\n' $URL "$token" \
       "$DIR"/sonar-scanner/bin/sonar-scanner "$pass" > $ENV)
  fi
  echo "SonarQube up at $URL; settings in $ENV" ;;
stop) docker rm -f $NAME >/dev/null 2>&1 || true; echo "stopped (data kept in $DIR)" ;;
*) sed -n 2,5p "$0" | sed 's/^# \{0,1\}//'; exit 1 ;;
esac
