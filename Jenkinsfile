#!/usr/bin/env groovy

// Learn groovy: https://learnxinyminutes.com/docs/groovy/

def docker_credentials = 'ecr:us-east-1:tailor_aws'
def recipes_yaml = 'rosdistro/config/recipes.yaml'

def testImage = { distribution, release_label, docker_registry -> docker_registry - "https://" + ':tailor-image-test-' + distribution + '-' + release_label }

def distributions = []
def organization = null

pipeline {
  agent none

  parameters {
    string(name: 'rosdistro_job', defaultValue: '/ci/toydistro/master')
    string(name: 'release_track', defaultValue: 'hotdog')
    string(name: 'release_label', defaultValue: 'hotdog')
    string(name: 'num_to_keep', defaultValue: '10')
    string(name: 'days_to_keep', defaultValue: '10')
    string(name: 'docker_registry')
    string(name: 'apt_repo')
    booleanParam(name: 'deploy', defaultValue: false)
  }

  options {
    timestamps()
  }

  stages {
    stage("Configure build parameters") {
      agent { label('master') }
      steps {
        script {
          sh('env')

          properties([
            buildDiscarder(logRotator(
              daysToKeepStr: params.days_to_keep, numToKeepStr: params.num_to_keep,
              artifactDaysToKeepStr: params.days_to_keep, artifactNumToKeepStr: params.num_to_keep
            ))
          ])

          copyArtifacts(
            projectName: params.rosdistro_job,
            selector: upstream(fallbackToLastSuccessful: true),
          )

          // (pbovbel) Read configuration from rosdistro. This should probably happen in some kind of Python
          def recipes_config = readYaml(file: recipes_yaml)
          organization = recipes_config['common']['organization']
          distributions = recipes_config['os'].collect {
            os, distribution -> distribution }.flatten()

          stash(name: 'rosdistro', includes: 'rosdistro/**')
        }
      }
      post {
        cleanup {
          deleteDir()
        }
      }
    }

    stage("Create test image") {
      agent none
      steps {
        script {
          def jobs = distributions.collectEntries { distribution ->
            [distribution, { node {
              try {
                dir('tailor-image') {
                  checkout(scm)
                }
                unstash(name: 'rosdistro')

                withCredentials([[$class: 'AmazonWebServicesCredentialsBinding', credentialsId: 'tailor_aws']]) {
                  test_image = docker.build(testImage(distribution, params.release_label, params.docker_registry),
                    "-f tailor-image/environment/Dockerfile --no-cache " +
                    "--build-arg OS_NAME=ubuntu " +
                    "--build-arg OS_VERSION=$distribution " +
                    "--build-arg APT_REPO=${params.apt_repo - 's3://'} " +
                    "--build-arg RELEASE_TRACK=$params.release_track " +
                    "--build-arg ORGANIZATION=$organization " +
                    "--build-arg AWS_ACCESS_KEY_ID=$AWS_ACCESS_KEY_ID " +
                    "--build-arg AWS_SECRET_ACCESS_KEY=$AWS_SECRET_ACCESS_KEY .")
                }
                docker.withRegistry(params.docker_registry, docker_credentials) {
                  if(params.deploy) {
                    test_image.push()
                  }
                }
              } finally {
                deleteDir()
                sh 'docker image prune -af --filter="until=3h" --filter="label=tailor" || true'
              }
            }}]
          }
          parallel(jobs)
        }
      }
    }
  }
}
