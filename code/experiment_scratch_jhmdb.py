from ExperimentBase import Pose_JHMDB

conf = {}

conf["batch_size"] = 1
conf["learning_rate"] = 1e-5
conf["nr_epochs"] = 100
conf["validation_amount"] = 0.1
conf["limit_data_percent"] = 1
conf["numpy_seed"] = 30004
conf["name"] = "scratch_jhmdb"
conf["num_blocks"] = 4
conf["nr_context"] = 0
conf["project_dir"] = ""
conf["evaluate_rate"] = 1

ft = Pose_JHMDB(conf, use_pretrained=False)
ft.run_experiment()
