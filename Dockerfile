FROM ubuntu:25.10

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl file git procps sudo ca-certificates \
    openssh-client openssh-server \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /run/sshd

RUN useradd -m -s /bin/bash dev && \
    echo "dev ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers

USER dev
WORKDIR /home/dev

RUN /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

ENV PATH="/home/linuxbrew/.linuxbrew/bin:${PATH}"

RUN brew install \
    neovim fish bat btop eza fd fzf just ncdu sops uv vivid zoxide chezmoi

RUN echo /home/linuxbrew/.linuxbrew/bin/fish | sudo tee -a /etc/shells && \
    sudo chsh -s /home/linuxbrew/.linuxbrew/bin/fish dev

COPY --chown=dev:dev . /home/dev/.local/share/chezmoi
RUN chezmoi init --apply

RUN mkdir -p ~/.ssh && chmod 700 ~/.ssh

EXPOSE 22
COPY --chmod=755 docker-entrypoint.sh /usr/local/bin/
ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["fish"]
