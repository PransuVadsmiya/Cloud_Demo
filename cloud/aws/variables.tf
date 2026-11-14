variable "region" {
  type    = string
  default = "ap-south-1" # Mumbai
}

variable "instance_type" {
  type    = string
  default = "t3.small" # 2 vCPU; t3 "unlimited" credits avoid CPU throttling during the test
}

variable "min_size" {
  type    = number
  default = 2
}

variable "max_size" {
  type    = number
  default = 12
}

variable "cpu_target" {
  type    = number
  default = 50 # faculty rule: scale out when average CPU goes above 50%
}
