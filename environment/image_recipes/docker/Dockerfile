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

# Extra args
ARG username
ARG password
ARG extra_arguments_ansible
ARG ansible_command
ARG description
ARG disk_size
ARG group

LABEL tailor=docker_image

ENV DEBIAN_FRONTEND=noninteractive \
    LANG=en_US.UTF-8 \
    PYTHONUNBUFFERED=1 \
    BUNDLE_ROOT=/opt/${ORGANIZATION}/${BUNDLE_VERSION}/${BUNDLE_FLAVOUR} \
    ANSIBLE_CONFIG=${ANSIBLE_CONFIG}

# Install basics
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    python3 \
    sudo \
    locales \
    ccache \
    gnupg \
    openssl \
    libtinyxml2-9 \  
    libboost-all-dev \
    tzdata && \
    locale-gen en_US.UTF-8 && \
    rm -rf /var/lib/apt/lists/*

# Add user
RUN groupadd -r "${username}" && \
    useradd -ms /bin/bash \
    -p "$(echo "${password}" | openssl passwd -1 -stdin)" \
    -g "$username" -G sudo "$username" && \
    echo "${username} ALL=(ALL) NOPASSWD: ALL" > /etc/sudoers && \
    mkdir -p /home/"${username}" && \
    usermod -d /home/"${username}" "${username}"

FROM base AS bundle

COPY bin ${BUNDLE_FOLDER}/bin
COPY share/locus_ansible ${BUNDLE_FOLDER}/share/locus_ansible
COPY librospack.so ${BUNDLE_FOLDER}/lib/librospack.so
COPY .vault_pass.txt /root/.vault_pass.txt

RUN cat > /tmp/default.inv <<'EOF'
[default]
default ansible_host=localhost ansible_connection=local
EOF

RUN bash -c "source ${BUNDLE_FOLDER}/share/locus_ansible/package.bash && \
    cd ${BUNDLE_FOLDER}/share/locus_ansible && \
    ${ansible_command} ${PLAYBOOK_FILE} \
    -i /tmp/default.inv \
    ${extra_arguments_ansible} \
    -e ansible_user=${username} \
    -e organization=${ORGANIZATION} \
    -e bundle_track=${BUNDLE_TRACK} \
    -e bundle_version=${BUNDLE_VERSION} \
    -e bundle_flavour=${BUNDLE_FLAVOUR} \
    -e ansible_host=default"

FROM bundle AS runtime

COPY rosdep.yaml /etc/ros/rosdep/rosdep.yaml
RUN echo "yaml file:///etc/ros/rosdep/rosdep.yaml" > /etc/ros/rosdep/sources.list.d/10-tailor.list && \
    rosdep update && \
    rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

COPY entrypoint.sh /bin/entrypoint.sh

USER ${username}
WORKDIR /home/${username}
ENTRYPOINT [ "/bin/entrypoint.sh" ]
