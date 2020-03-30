from invoke import task, run


@task()
def serve(ctx):
    run('echo "Building image \"weblate-dev\"..."')
    run('docker build -t weblate-dev --file mscli-Dockerfile .')
    run('docker-compose -f dev-docker/docker-compose.yml up')
