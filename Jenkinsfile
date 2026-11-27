// Jenkins CI/CD pipeline for Maply.
//
// Mirrors the GitHub Actions checks in .github/workflows/ci.yml (lint, Python
// tests, JavaScript checks), then packages a release archive and, on main,
// optionally triggers a deployment.
//
// Agent requirements: a Linux agent with python3 (3.10+, with venv) and
// Node.js 20+ on PATH. Required plugins: Pipeline, Git, Credentials Binding.
//
// Deployment: create a "Secret text" credential with the ID
// `maply-deploy-hook` holding your hosting provider's deploy-hook URL
// (Render, Railway, etc.). The Deploy stage runs only on main and only when
// the DEPLOY parameter is ticked.

pipeline {
    agent any

    options {
        timestamps()
        timeout(time: 20, unit: 'MINUTES')
        buildDiscarder(logRotator(numToKeepStr: '20'))
        disableConcurrentBuilds(abortPrevious: true)
    }

    parameters {
        booleanParam(name: 'DEPLOY', defaultValue: true,
                     description: 'Trigger the deploy hook after a successful build on main.')
    }

    environment {
        VENV = "${WORKSPACE}/.venv"
        PIP_DISABLE_PIP_VERSION_CHECK = '1'
        PYTHONDONTWRITEBYTECODE = '1'
    }

    stages {
        stage('Checkout') {
            steps {
                checkout scm
            }
        }

        stage('Set up Python') {
            steps {
                sh '''
                    python3 --version
                    python3 -m venv "$VENV"
                    . "$VENV/bin/activate"
                    python -m pip install --upgrade pip
                    pip install -r requirements.txt flake8
                '''
            }
        }

        stage('Checks') {
            parallel {
                stage('Lint (Python)') {
                    steps {
                        sh '''
                            . "$VENV/bin/activate"
                            flake8 . --select=E9,F63,F7,F82 \
                                --exclude=.venv,venv,.codex-test-deps \
                                --show-source --statistics
                        '''
                    }
                }

                stage('Python tests') {
                    steps {
                        sh '''
                            . "$VENV/bin/activate"
                            python -m unittest discover -s tests -v
                        '''
                    }
                }

                stage('JavaScript checks') {
                    steps {
                        sh '''
                            node --version
                            for file in static/js/*.js; do
                                node --input-type=module --check < "$file"
                            done
                            node --test "tests/js/*.test.mjs"
                        '''
                    }
                }
            }
        }

        stage('Package') {
            steps {
                sh '''
                    mkdir -p dist
                    git archive --format=tar.gz \
                        --prefix="maply-${BUILD_NUMBER}/" \
                        -o "dist/maply-${BUILD_NUMBER}.tar.gz" HEAD
                '''
                archiveArtifacts artifacts: 'dist/*.tar.gz', fingerprint: true
            }
        }

        stage('Deploy') {
            when {
                allOf {
                    branch 'main'
                    expression { return params.DEPLOY }
                }
            }
            steps {
                withCredentials([string(credentialsId: 'maply-deploy-hook', variable: 'DEPLOY_HOOK_URL')]) {
                    sh 'curl --fail --silent --show-error -X POST "$DEPLOY_HOOK_URL"'
                }
            }
        }
    }

    post {
        success {
            echo "Maply build #${env.BUILD_NUMBER} passed."
        }
        failure {
            echo "Maply build #${env.BUILD_NUMBER} failed. Check the stage logs above."
        }
        always {
            sh 'rm -rf "$VENV"'
        }
    }
}
