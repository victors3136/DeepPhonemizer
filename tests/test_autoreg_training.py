import os
import shutil
import tempfile
import unittest
from pathlib import Path

import numpy as np
import torch

from DeepPhonemizer.dp import preprocess
from DeepPhonemizer.dp.model.model import AutoregressiveTransformer
from DeepPhonemizer.dp.model.predictor import Predictor
from DeepPhonemizer.dp.preprocess import preprocess
from DeepPhonemizer.dp.train import train
from DeepPhonemizer.dp.utils.io import read_config, save_config


class TestAutoregTraining(unittest.TestCase):

    def setUp(self) -> None:
        torch.manual_seed(42)
        np.random.seed(42)
        temp_dir = tempfile.mkdtemp(prefix='TestPreprocessTmp')
        self.temp_dir = Path(temp_dir)
        test_path = os.path.dirname(os.path.abspath(__file__))
        self.test_config_path = Path(test_path) / 'resources/autoreg_test_config.yaml'

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_autoregtraining_happy_path(self) -> None:
        config = read_config(self.test_config_path)
        data_dir = self.temp_dir / 'datasets'
        checkpoint_dir = self.temp_dir / 'checkpoints'
        config_path = self.temp_dir / 'autoreg_test_config.yaml'
        config['paths']['data_dir'] = str(data_dir)
        config['paths']['checkpoint_dir'] = str(checkpoint_dir)
        save_config(config, config_path)

        train_data = [
            ('en_us', 'young', 'jʌŋ'),
            ('de', 'benützten', 'bənʏt͡stn̩'),
            ('de', 'gewürz', 'ɡəvʏʁt͡s')
        ] * 100

        val_data = [
            ('en_us', 'young', 'jʌŋ'),
            ('de', 'gewürz', 'ɡəvʏʁt͡s')
        ] * 10

        preprocess(config_file=config_path,
                   train_data=train_data,
                   val_data=val_data,
                   deduplicate_train_data=False)

        train(rank=0, num_gpus=0, config_file=config_path)

        predictor = Predictor.from_checkpoint(checkpoint_dir / 'latest_model.pt')

        self.assertTrue(isinstance(predictor.model, AutoregressiveTransformer))

        result = predictor(words=['young'], lang='en_us')[0]
        self.assertEqual('jʌŋ', result.phonemes)
        self.assertTrue(result.confidence > 0.98)

        result = predictor(words=['gewürz'], lang='de')[0]
        self.assertEqual('ɡəvʏʁt͡s', result.phonemes)
        self.assertTrue(result.confidence > 0.96)

        result = predictor(words=['gewürz'], lang='en_us')[0]
        self.assertTrue(0.8 < result.confidence < 0.84)

        # test jit export
        predictor.model = torch.jit.script(predictor.model)
        result_jit = predictor(words=['gewürz'], lang='en_us')[0]
        self.assertEqual(result.phonemes, result_jit.phonemes)
        self.assertEqual(result.confidence, result_jit.confidence)
