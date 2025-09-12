import sys
from package_deploy.deploy import PackageDeploy

PackageDeploy(sys.argv[1:]).deploy()