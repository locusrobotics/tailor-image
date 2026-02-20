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
    . /run/secrets/creds && \
    groupadd -r "${USERNAME}" && \
    useradd -ms /bin/bash \
    -p "$(echo "${PASSWORD}" | openssl passwd -1 -stdin)" \
    -g "$USERNAME" -G sudo "$USERNAME" && \
    echo "${USERNAME} ALL=(ALL) NOPASSWD: ALL" >> /etc/sudoers && \
    mkdir -p /home/"${USERNAME}" && \
    usermod -d /home/"${USERNAME}" "${USERNAME}"

FROM base AS bundle

# Add package mirror
RUN apt-get update && apt-get install --no-install-recommends -y apt-transport-https apt-transport-s3 && \
    apt-key adv --keyserver keyserver.ubuntu.com --recv-keys 142D5F1683E1528B && \
    echo "deb [arch=amd64] ${APT_REPO}/${BUNDLE_VERSION}/ubuntu ${OS_VERSION} main" >> /etc/apt/sources.list && \
    echo "deb [arch=amd64] ${APT_REPO}/${BUNDLE_VERSION}/ubuntu ${OS_VERSION}-mirror ${OS_VERSION}" >> /etc/apt/sources.list

RUN --mount=type=secret,id=aws_secret \
    . /run/secrets/aws_secret && \
    echo "AccessKeyId = $AWS_ACCESS_KEY_ID" | tee /etc/apt/s3auth.conf && \
    echo "SecretAccessKey = $AWS_SECRET_ACCESS_KEY" | tee -a /etc/apt/s3auth.conf && \
    echo "Token = ''" | tee -a /etc/apt/s3auth.conf && \
    echo "Region = 'us-east-1'" | tee -a /etc/apt/s3auth.conf

# Install bundle
RUN apt-get update && \
    RTI_NC_LICENSE_ACCEPTED=yes apt-get install --no-install-recommends -qy\
    ${ORGANIZATION}-${BUNDLE_FLAVOUR}-${BUNDLE_VERSION}  && \
    rm -rf /var/lib/apt/lists/*

FROM bundle AS runtime

COPY entrypoint.sh /bin/entrypoint.sh

USER ${USERNAME}
WORKDIR /home/${USERNAME}
ENTRYPOINT [ "/bin/entrypoint.sh" ]