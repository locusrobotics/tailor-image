ARG OS_NAME=ubuntu
ARG OS_VERSION=jammy

FROM ${OS_NAME}:${OS_VERSION} AS base

ARG TYPE
ARG BUNDLE_FLAVOUR
ARG IMAGE_NAME
ARG ECR_SERVER
ARG ECR_REPOSITORY
ARG PLAYBOOK_FILE
ARG BUNDLE_FOLDER
ARG ORGANIZATION
ARG BUNDLE_TRACK
ARG BUNDLE_VERSION
ARG ANSIBLE_CONFIG
ARG OS_NAME=ubuntu
ARG OS_VERSION=jammy

# Extra args
ARG username
ARG password
ARG extra_arguments_ansible
ARG ansible_command
ARG description
ARG disk_size
ARG group

ARG AWS_ACCESS_KEY_ID
#ARG AWS_SECRET_ACCESS_KEY

LABEL tailor=docker_image

ENV DEBIAN_FRONTEND=noninteractive \
    LANG=en_US.UTF-8 \
    PYTHONUNBUFFERED=1 \
    BUNDLE_ROOT=/opt/${ORGANIZATION}/${BUNDLE_VERSION}/${BUNDLE_FLAVOUR} \
    ANSIBLE_CONFIG=${ANSIBLE_CONFIG} \
    AWS_ACCESS_KEY_ID=${AWS_ACCESS_KEY_ID}
#AWS_SECRET_ACCESS_KEY=${AWS_SECRET_ACCESS_KEY}

# Install basics
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    python3 \
    sudo \
    locales \
    ccache \
    gnupg \
    openssl \
    libboost-all-dev \
    ca-certificates \
    tzdata && \
    locale-gen en_US.UTF-8 && \
    rm -rf /var/lib/apt/lists/*

#librospack-dev \

# Add user
RUN groupadd -r "${username}" && \
    useradd -ms /bin/bash \
    -p "$(echo "${password}" | openssl passwd -1 -stdin)" \
    -g "$username" -G sudo "$username" && \
    echo "${username} ALL=(ALL) NOPASSWD: ALL" >> /etc/sudoers && \
    mkdir -p /home/"${username}" && \
    usermod -d /home/"${username}" "${username}"

FROM base AS bundle

# Add package mirror
RUN apt-get update && apt-get install --no-install-recommends -y apt-transport-https apt-transport-s3 && \
    apt-key adv --keyserver keyserver.ubuntu.com --recv-keys 142D5F1683E1528B && \
    echo "deb [arch=amd64] s3://locus-tailor-artifacts/${BUNDLE_VERSION}/ubuntu ${OS_VERSION} main" >> /etc/apt/sources.list && \
    echo "deb [arch=amd64] s3://locus-tailor-artifacts/${BUNDLE_VERSION}/ubuntu ${OS_VERSION}-mirror ${OS_VERSION}" >> /etc/apt/sources.list

RUN --mount=type=secret,id=aws_secret \
    export AWS_SECRET_ACCESS_KEY=$(cat /run/secrets/aws_secret) \
    echo "AccessKeyId = $AWS_ACCESS_KEY_ID" | tee /etc/apt/s3auth.conf && \
    echo "SecretAccessKey = $AWS_SECRET_ACCESS_KEY" | tee -a /etc/apt/s3auth.conf && \
    echo "Token = ''" | tee -a /etc/apt/s3auth.conf && \
    echo "Region = 'us-east-1'" | tee -a /etc/apt/s3auth.conf


RUN apt-get update && \
    RTI_NC_LICENSE_ACCEPTED=yes apt-get install --no-install-recommends -qy\
    ${ORGANIZATION}-${BUNDLE_FLAVOUR}-${BUNDLE_VERSION}  && \
    rm -rf /var/lib/apt/lists/*

COPY .vault_pass.txt /root/.vault_pass.txt

RUN cat > /tmp/default.inv <<'EOF'
[default]
default ansible_host=localhost ansible_connection=local
EOF

RUN bash -c "source ${BUNDLE_FOLDER}/setup.bash && \
    ${ansible_command} ${PLAYBOOK_FILE} \
    -i /tmp/default.inv \
    ${extra_arguments_ansible} \
    -e ansible_user=${username} \
    -e organization=${ORGANIZATION} \
    -e bundle_track=${BUNDLE_TRACK} \
    -e bundle_version=${BUNDLE_VERSION} \
    -e bundle_flavour=${BUNDLE_FLAVOUR} \
    -e ansible_host=default \
    --vault-password-file=/root/.vault_pass.txt"

FROM bundle AS runtime

COPY entrypoint.sh /bin/entrypoint.sh

USER ${username}
WORKDIR /home/${username}
ENTRYPOINT [ "/bin/entrypoint.sh" ]
