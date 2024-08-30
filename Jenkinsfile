// Function to check if a date string matches the MM/DD/YYYY format
boolean isDateValid(String dateStr) {
    // Regular expression to match MM/DD/YYYY format
    def pattern = ~/^(0[1-9]|1[0-2])\/(0[1-9]|[12][0-9]|3[01])\/\d{4}$/
    return dateStr ==~ pattern
}

pipeline {
    agent { label 'linux' }
    
	parameters {
		string (name: 'ticketnumber', description: 'Ticket number', defaultValue: 'WorkingJenkins')
		string (name: 'startDate', description: 'MM/DD/YYYY', defaultValue: 'MM/DD/YYYY')
		string (name: 'endDate', description: 'MM/DD/YYYY', defaultValue: 'MM/DD/YYYY')
		text (name: 'servernames', description: 'List of servers that this srcipt will add the new tag', defaultValue: 'useadvss1upd1\nuseadvss1upd2')
		choice (name : 'awsenvironment',
            choices : ['deltekdev','dco','flexplus','costpoint','goss'],
            description : 'Product where jenkins will add tags.')
	
	}

    stages {
        stage('Checkout Source') {
            steps {
                sh 'python3 --version'
                sh 'pip3 install pandas'
                checkout([$class: 'GitSCM', branches: [[name: "*/main"]], doGenerateSubmoduleConfigurations: false, extensions: [], submoduleCfg: [], userRemoteConfigs: [[url: "https://github.com/RodGuiamoy/QuickCreateDashboardAbsolute.git"]]])
            }
        }
        stage('Execute Shell') {
            steps {
                script {
                    def awsCredential = null
					// def input_day_range = "${params['days']}"
					// def day_range = 60
					// try {
					// 	def valid_day_range = input_day_range.toInteger()
					// 	if (valid_day_range < 1 || valid_day_range > 60) {
					// 		// Set to default value of 60 if out of range
					// 		day_range = 60
					// 		println "Day range was invalid. Setting to default value: ${day_range}"
					// 	} else {
					// 		println "Day range is valid: ${valid_day_range}"
					// 		day_range = valid_day_range
					// 	}
					// } catch (NumberFormatException e) {
					// 	// Handle the case where the value is not a valid integer
					// 	day_range = 60
					// 	println "Day range was invalid or not a number. Setting to default value: ${day_range}"
					// }

					def startDate = "${params['startDate']}"
					def endDate = "${params['endDate']}"

					if (!isDateValid(startDate)) {
						error("The start date ${startDate} is NOT in MM/DD/YYYY format.")
					} 

					if (!isDateValid(endDate)) {
						error("The date ${endDate} is NOT in MM/DD/YYYY format.")
					} 

                    def awsEnvironment = "${params['awsenvironment']}"
                    def inputservernames = "${params['servernames']}"
					def serverlist = inputservernames.split('\n')
					println "server '${serverlist}'"
					println "environment  '${awsEnvironment}'"

					
                    switch(awsEnvironment) {
                        case 'deltekdev':
                            awsCredential = 'infra-at-dev'
                            break
                        case 'dco':
                            awsCredential = 'infra-at-dco'
                            break
                        case 'flexplus':
                            awsCredential = 'infra-at-flexplus'
                            break    
                        case 'costpoint':
                            awsCredential = 'infra-at-costpoint'
                            break  
                    }                    
                    withCredentials([[$class: 'AmazonWebServicesCredentialsBinding',credentialsId: "${awsCredential}", accessKeyVariable: 'AWS_ACCESS_KEY_ID', secretKeyVariable: 'AWS_SECRET_ACCESS_KEY']]) 
					{
						for (server in serverlist){
								def servername = server.toUpperCase().replaceAll(/\s+/, '')
								def regioncode = servername.take(4)
								def awsRegion = null
								println "region '${regioncode}'"
								
								
								switch (regioncode) {
								case 'USEA':
									awsRegion = "us-east-1"
									break
								case 'USWE':
									awsRegion = "us-west-2"
									break
								case 'EUWE':
									awsRegion = "eu-west-1"
									break
								case 'EUCE':
									awsRegion = "eu-central-1"
									break
								case 'APAU':
									awsRegion = "ap-southeast-2"
									break
								case 'APSP':
									awsRegion = "ap-southeast-1"
									break
								case 'CACE':
									awsRegion = "ca-central-1"
									break
								}

								println "'${servername}'"
								println "aws region '${awsRegion}'"
								// println "Days covered for assessment '${day_range}'"
								sh "python3 infrasre_create_dashboard_fullassessment.py '${servername}' '${awsRegion}' '${startDate}' '${endDate}'"
						}
					}
            }	}
        }
    }
}

