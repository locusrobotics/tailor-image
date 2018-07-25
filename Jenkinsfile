#!/usr/bin/env groovy

// Learn groovy: https://learnxinyminutes.com/docs/groovy/

def docker_registry = '084758475884.dkr.ecr.us-east-1.amazonaws.com/tailor-image'
def docker_registry_uri = 'https://' + docker_registry
def docker_credentials = 'ecr:us-east-1:tailor_aws'

def days_to_keep = 10
def num_to_keep = 10

def testImage = { distribution -> docker_registry + ':jenkins-' + distribution + '-test-image' }

timestamps {
  stage("Configure build parameters") {
    node('master') {
      sh 'env'
      cancelPreviousBuilds()

      def triggers = [
        upstream(upstreamProjects: '../tailor-distro/' + env.BRANCH_NAME, threshold: hudson.model.Result.SUCCESS)
      ]
      properties([
        buildDiscarder(logRotator(
          artifactDaysToKeepStr: days_to_keep.toString(), artifactNumToKeepStr: num_to_keep.toString(),
          daysToKeepStr: days_to_keep.toString(), numToKeepStr: num_to_keep.toString()
        )),
        pipelineTriggers(triggers)
      ])
    }
  }

  // TODO(pbovbel) read image params from rosdistro
  def distribution = 'xenial'

  // TODO(pbovbel) build a matrix of images and types using groovy or a framework like  packer
  stage('Create test image') {
    node {
      try {
        dir('tailor-image') {
          checkout(scm)
        }

        def test_image = docker.image(testImage(distribution))
        try {
           docker.withRegistry(docker_registry_uri, docker_credentials) { test_image.pull() }
        } catch (all) {
          echo "Unable to pull ${testImage(distribution)} as a build cache"
        }

        withCredentials([[$class: 'AmazonWebServicesCredentialsBinding', credentialsId: 'tailor_aws']]) {
          test_image = docker.build(testImage(distribution),
            "-f tailor-image/environment/Dockerfile --cache-from ${testImage(distribution)} " +
            "--build-arg AWS_ACCESS_KEY_ID=$AWS_ACCESS_KEY_ID " +
            "--build-arg AWS_SECRET_ACCESS_KEY=$AWS_SECRET_ACCESS_KEY .")
        }
        docker.withRegistry(docker_registry_uri, docker_credentials) {
          test_image.push()
        }

      } finally {
        deleteDir()
        // If two docker prunes run simulataneously, one will fail, hence || true
        sh 'docker image prune -af --filter="until=3h" --filter="label=tailor" || true'
      }
    }
  }
}


@NonCPS
def cancelPreviousBuilds() {
    def jobName = env.JOB_NAME
    def buildNumber = env.BUILD_NUMBER.toInteger()
    /* Get job name */
    def currentJob = Jenkins.instance.getItemByFullName(jobName)

    /* Iterating over the builds for specific job */
    for (def build : currentJob.builds) {
        /* If there is a build that is currently running and it's older than current build */
        if (build.isBuilding() && build.number.toInteger() < buildNumber) {
            /* Than stopping it */
            build.doStop()
        }
    }
}
