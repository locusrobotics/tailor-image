ARG OS_NAME=ubuntu
ARG OS_VERSION=xenial
FROM ${OS_NAME}:${OS_VERSION}

LABEL tailor="dev_image"

ARG AWS_ACCESS_KEY_ID
ENV AWS_ACCESS_KEY_ID ${AWS_ACCESS_KEY_ID}

ARG AWS_SECRET_ACCESS_KEY
ENV AWS_SECRET_ACCESS_KEY ${AWS_SECRET_ACCESS_KEY}

ARG OS_NAME
ARG OS_VERSION
ARG APT_REPO
ARG RELEASE_TRACK
ARG ORGANIZATION
ARG FLAVOUR
ENV BUNDLE_ROOT /opt/${ORGANIZATION}/${RELEASE_TRACK}/${FLAVOUR}

SHELL ["/bin/bash", "-c"]

ENV DEBIAN_FRONTEND noninteractive
ENV PYTHONUNBUFFERED 1

RUN apt-get update && apt-get install --no-install-recommends -y locales sudo ccache
RUN locale-gen en_US.UTF-8
ENV LANG en_US.UTF-8

# TODO(pbovbel) repack boto to avoid pip hacks
RUN apt-get install -y python-all-dev python-pip python-setuptools python-wheel && \
    apt-key adv --keyserver keyserver.ubuntu.com --recv-keys 379CE192D401AB61 && \
    echo "deb http://dl.bintray.com/lucidsoftware/apt/ lucid main" >> /etc/apt/sources.list && \
    apt-get update && apt-get install -y apt-boto-s3

# pending https://github.com/colcon/colcon-cmake/issues/34
RUN apt-key adv --keyserver keyserver.ubuntu.com --recv-keys 142D5F1683E1528B && \
    echo "deb [arch=amd64] s3://s3.amazonaws.com/$APT_REPO/$RELEASE_TRACK/$OS_NAME $OS_VERSION main" >> /etc/apt/sources.list && \
    echo "deb [arch=amd64] s3://s3.amazonaws.com/$APT_REPO/$RELEASE_TRACK/$OS_NAME $OS_VERSION-mirror main" >> /etc/apt/sources.list && \
    apt-get update && apt-get dist-upgrade -y && \
    RTI_NC_LICENSE_ACCEPTED=yes apt-get install -y \
        $ORGANIZATION-$FLAVOUR-$RELEASE_TRACK \
        python3-colcon-common-extensions \
        cmake

# TODO(pbovbel) colcon fails with older setuptools
RUN apt-get install -y python3-pip && \
    python3 -m pip install setuptools -U

# Inject the rosdep definitions from source
RUN rosdep init
RUN echo "yaml file:///etc/ros/rosdep/rosdep.yaml" > /etc/ros/rosdep/sources.list.d/10-tailor.list
COPY rosdistro/rosdep/rosdep.yaml /etc/ros/rosdep/rosdep.yaml

# Install packages to make dev's lifes easier
RUN apt-get update && apt-get install --no-install-recommends -y vim emacs nano git

RUN apt-get install -y python3-pip && \
    python3 -m pip install catkin_tools -U

# Create non-root user
RUN groupadd -r tailor && useradd -ms /bin/bash -g tailor -G sudo tailor
RUN echo "tailor ALL=(ALL) NOPASSWD: ALL" > /etc/sudoers
USER tailor
RUN mkdir -p /home/tailor && \
    usermod -d /home/tailor tailor

# Rosdep fails for fuerte.yaml, so we need || true to not fail
RUN rosdep update || true
