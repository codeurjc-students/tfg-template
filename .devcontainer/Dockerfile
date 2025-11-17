FROM ubuntu:latest

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
    && apt-get -y install --no-install-recommends apt-utils 2>&1

# Verify git and needed tools are installed
RUN apt-get install --no-install-recommends -y git procps

# Install Tex Live
RUN apt-get update && apt-get -y upgrade \
    && apt-get -y install --no-install-recommends texlive-full \
    && apt-get autoremove -y \
    && apt-get clean -y \
    && rm -rf /var/lib/apt/lists/*
    
ENV DEBIAN_FRONTEND=dialog \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8