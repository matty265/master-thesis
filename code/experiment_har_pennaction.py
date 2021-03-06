from ExperimentBase import HAR_PennAction

conf = {}

conf["learning_rate"] = 2e-5
conf["validation_amount"] = 0.1 # 10 percent
conf["numpy_seed"] = 30004
conf["num_blocks"] = 4
conf["nr_context"] = 2
conf["project_dir"] = "har_pennaction"

conf["batch_size"] = 10
conf["val_batch_size"] = 1
conf["total_iterations"] = 80000
conf["evaluate_rate"] =  1000
conf["limit_data_percent"] = 1 # limit dataset to x percent (for testing)
conf["use_gt_bb"] = True
conf["use_gt_pose"] = False

conf["fine_tune"] = False # otherwise, using gt pose would make no sense
conf["name"] = "without_finetune_with_td"
conf["use_timedistributed"] = True
har = HAR_PennAction(conf)
har.run_experiment()

# conf["fine_tune"] = True
# conf["use_gt_bb"] = True
# conf["use_gt_pose"] = False
# conf["start_finetuning"] = 20000
# conf["lr_milestones"] = [20000]
# conf["name"] = "with_finetune"
# har = HAR_PennAction(conf)
# har.run_experiment()
