ARG OS_NAME=ubuntu
ARG OS_VERSION=jammy

FROM ${OS_NAME}:${OS_VERSION} AS base

ARG ORGANIZATION
ARG BUNDLE_FLAVOUR
ARG BUNDLE_VERSION
ARG OS_NAME=ubuntu
ARG OS_VERSION=jammy
ARG AWS_ACCESS_KEY_ID
ARG USERNAME
ARG APT_REPO
ARG ENTRYPOINT_PATH

LABEL tailor=docker_image

ENV DEBIAN_FRONTEND=noninteractive \
    LANG=en_US.UTF-8 \
    PYTHONUNBUFFERED=1 \
    BUNDLE_ROOT=/opt/${ORGANIZATION}/${BUNDLE_VERSION}/${BUNDLE_FLAVOUR} \
    AWS_ACCESS_KEY_ID=${AWS_ACCESS_KEY_ID}

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

# Add user
RUN --mount=type=secret,id=creds \
    PASSWORD="$(cat /run/secrets/creds)"; \
    UBUNTU_CODENAME="$(. /etc/os-release 2>/dev/null || true; echo "${UBUNTU_CODENAME:-}")"; \
    if [ "$UBUNTU_CODENAME" = "noble" ] && id ubuntu >/dev/null 2>&1; then \
        echo "Renaming default 'ubuntu' user to '${USERNAME}'"; \
        usermod -l "${USERNAME}" ubuntu; \
        groupmod -n "${USERNAME}" ubuntu; \
    else \
        echo "Creating new '${USERNAME}' user and group"; \
        useradd -m -d "/home/${USERNAME}" "${USERNAME}"; \
    fi; \
    usermod -m -s /bin/bash \
    -p "$(printf '%s' "$PASSWORD" | openssl passwd -1 -stdin)" \
    -d "/home/$USERNAME" \
    -G sudo "$USERNAME"; \
    echo "$USERNAME ALL=(ALL) NOPASSWD: ALL" >> /etc/sudoers

FROM base AS bundle

# Add package mirror
RUN apt-get update && apt-get install --no-install-recommends -y apt-transport-https apt-transport-s3 && \
    apt-key adv --keyserver keyserver.ubuntu.com --recv-keys 142D5F1683E1528B && \
    echo "deb [arch=amd64] ${APT_REPO}/${BUNDLE_VERSION}/ubuntu ${OS_VERSION} main" >> /etc/apt/sources.list.d/tailor.list && \
    echo "deb [arch=amd64] ${APT_REPO}/${BUNDLE_VERSION}/ubuntu ${OS_VERSION}-mirror ${OS_VERSION}" >> /etc/apt/sources.list.d/tailor.list

RUN --mount=type=secret,id=aws_secret \
    AWS_SECRET_ACCESS_KEY="$(cat /run/secrets/aws_secret)" && \
    echo "AccessKeyId = $AWS_ACCESS_KEY_ID" | tee /etc/apt/s3auth.conf && \
    echo "SecretAccessKey = $AWS_SECRET_ACCESS_KEY" | tee -a /etc/apt/s3auth.conf && \
    echo "Token = ''" | tee -a /etc/apt/s3auth.conf && \
    echo "Region = 'us-east-1'" | tee -a /etc/apt/s3auth.conf

# Install bundle
RUN apt-get update && \
    RTI_NC_LICENSE_ACCEPTED=yes apt-get install --no-install-recommends -qy\
    ${ORGANIZATION}-${BUNDLE_FLAVOUR}-${BUNDLE_VERSION}  && \
    rm -rf /var/lib/apt/lists/* && \
    rm -f /etc/apt/s3auth.conf && \
    rm -f /etc/apt/sources.list.d/tailor.list

FROM bundle AS runtime

COPY ${ENTRYPOINT_PATH} /bin/entrypoint.sh

USER ${USERNAME}
WORKDIR /home/${USERNAME}
ENTRYPOINT [ "/bin/entrypoint.sh" ]
