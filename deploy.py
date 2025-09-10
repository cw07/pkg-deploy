import sys
from package_deploy.publish import PackageDeploy

PackageDeploy(sys.argv[1:]).deploy()