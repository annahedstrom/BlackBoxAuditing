from AbstractModelFactory import AbstractModelFactory
from AbstractModelVisitor import AbstractModelVisitor
from collections import OrderedDict
import subprocess
import io
import csv
import os

WEKA_PATH = "/usr/share/java/weka.jar"
TMP_DIR = "tmp/"
# Create the TMP_DIR if it does not already exist.
if not os.path.exists(TMP_DIR):
  os.makedirs(TMP_DIR)

class ModelFactory(AbstractModelFactory):

  def __init__(self, *args, **kwargs):
    super(ModelFactory, self).__init__(*args,**kwargs)

    #self.kernel = "" # Weka defaults to a traditional linear classifier.
    self.kernel = "weka.classifiers.functions.supportVector.Puk -O 0.5 -S 7"

  def build(self, train_set):

    # Prepare the ARFF file that will train the model.
    arff_types = get_arff_type_dict(self.headers, self.all_data)
    model_file = TMP_DIR + "SVM_{}.model".format(self.model_name)
    train_arff_file = model_file + ".train.arff"
    list_to_arff_file(arff_types, train_set, train_arff_file)

    response_index = self.headers.index(self.response_header)

    # Call WEKA to generate the model file.
    command = "java weka.classifiers.functions.SMO -t {} -d {} -p 0 -c {}".format(train_arff_file, model_file, response_index + 1)

    # If a kernel option is listed, include it in the command.
    if self.kernel:
      command += " -K \"{}\"".format(self.kernel)

    run_weka_command(command)

    return ModelVisitor(model_file, arff_types, response_index)


class ModelVisitor(AbstractModelVisitor):

  def __init__(self, model_file, arff_types, response_index):
    self.model_file = model_file
    self.arff_types = arff_types
    self.response_index = response_index

  def test(self, test_set):
    test_arff_file = self.model_file +".test.arff"
    list_to_arff_file(self.arff_types, test_set, test_arff_file)
    results_path = "{}.out".format(test_arff_file)

    # Produce predictions for the test set.
    # Note: The "-c" option is 1-indexed by Weka
    command = "java weka.classifiers.functions.SMO -T {} -l {} -p 0 -c {} 1> {}".format(test_arff_file, self.model_file, self.response_index+1, results_path)
    run_weka_command(command)

    # Read the output file.
    prediction_index = 2
    with open(results_path, "r") as f:
      raw_lines = f.readlines()[5:-1] # Discard the headers and ending line.
      raw_predictions = [line.split()[prediction_index] for line in raw_lines]
      predictions = [prediction.split(":")[1] for prediction in raw_predictions]

    # Produce a confusion matrix in a dictionary format from those predictions.
    conf_table = {}
    for entry, guess in zip(test_set, predictions):
      actual = entry[self.response_index]

      if not actual in conf_table:
        conf_table[actual] = {}

      if not guess in conf_table[actual]:
        conf_table[actual][guess] = 1
      else:
        conf_table[actual][guess] += 1

    return conf_table


def run_weka_command(command):
  set_path = "export CLASSPATH=$CLASSPATH:{}; ".format(WEKA_PATH)
  subprocess.check_output(set_path + command, shell=True)


def get_arff_type_dict(headers, data):
  values = {header:[row[i] for row in data] for i, header in enumerate(headers)}
  arff_type = OrderedDict()
  for header in headers:
    if all( map(lambda x: isinstance(x, float), values[header]) ):
      arff_type[header] = "numeric"
    elif all( map(lambda x: isinstance(x, int), values[header]) ):
      arff_type[header] = "numeric"
    else:
      arff_type[header] = sorted(set(values[header])) # Categorical
  return arff_type


def list_to_arff_file(arff_type_dict, data, arff_file_output):
  # Produce the relevant file headers for the ARFF.
  arff_header = "@relation BlackBoxAuditing\n"
  for attribute, types in arff_type_dict.items():
    if type(types) == list:
      types = "{" + ",".join(str(entry) for entry in types) + "}"
    attribute = attribute.replace(" ","_")
    arff_header += "@attribute {} {}\n".format(attribute, types)

  arff_header += "\n@data\n"

  # Write the data in a CSV-like format to avoid weird escaping issues.
  data_output = io.BytesIO()
  csv_writer = csv.writer(data_output)
  for row in data:
    csv_writer.writerow(row)

  # Dump everything into the intended ARFF file.
  with open(arff_file_output, "w") as f:
    f.write(arff_header + data_output.getvalue())


def test():
  headers = ["predictor", "response"]
  train_set = [[i, "A"] for i in range(1,50)] + [[i, "B"] for i in range(51,100)]
  # Purposefully replace "B" with "C" so that we *should* fail them.
  test_set = [[i, "A"] for i in range(1,50)] + [[i, "C"] for i in range(51,100)]
  all_data = train_set + test_set

  factory = ModelFactory(all_data, headers, "response", name_prefix="test")
  model = factory.build(train_set)
  print "factory builds ModelVisitor? -- ", isinstance(model, ModelVisitor)

  predictions = model.test(test_set)
  intended_predictions = {'A': {'A': 49}, 'C': {'B': 49}}
  print "predicting correctly? -- ", predictions == intended_predictions

if __name__=="__main__":
  test()