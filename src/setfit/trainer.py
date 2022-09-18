import math
from typing import Optional, Union

import evaluate
import numpy as np
from sentence_transformers import InputExample, losses
from sentence_transformers.datasets import SentenceLabelDataset
from sentence_transformers.losses.BatchHardTripletLoss import BatchHardTripletLossDistanceFunction
from torch.utils.data import DataLoader

from setfit.modeling import SupConLoss, sentence_pairs_generation


class SetFitTrainer:
    def __init__(
        self,
        model=None,
        train_dataset=None,
        eval_dataset=None,
        compute_metrics=None,
        loss_class=None,
        num_epochs=None,
        learning_rate=None,
        batch_size=None,
    ):

        self.model = model
        self.train_dataset = train_dataset
        self.eval_dataset = eval_dataset
        self.compute_metrics = compute_metrics
        self.loss_class = loss_class
        self.num_epochs = num_epochs
        self.learning_rate = learning_rate
        self.batch_size = batch_size

    def train(self):
        # self.model.model_body.load_state_dict(copy.deepcopy(self.model.model_original_state))
        x_train = self.train_dataset["text"]
        y_train = self.train_dataset["label"]

        if self.loss_class is None:
            return

        # sentence-transformers adaptation
        batch_size = self.batch_size
        if self.loss_class in [
            losses.BatchAllTripletLoss,
            losses.BatchHardTripletLoss,
            losses.BatchSemiHardTripletLoss,
            losses.BatchHardSoftMarginTripletLoss,
            SupConLoss,
        ]:
            train_examples = [InputExample(texts=[text], label=label) for text, label in zip(x_train, y_train)]
            train_data_sampler = SentenceLabelDataset(train_examples)

            batch_size = min(self.args.batch_size, len(train_data_sampler))
            train_dataloader = DataLoader(train_data_sampler, batch_size=batch_size, drop_last=True)

            if self.loss_class is losses.BatchHardSoftMarginTripletLoss:
                train_loss = self.loss_class(
                    model=self.model,
                    distance_metric=BatchHardTripletLossDistanceFunction.cosine_distance,
                )
            elif self.loss_class is SupConLoss:
                train_loss = self.loss_class(model=self.model)
            else:
                train_loss = self.loss_class(
                    model=self.model,
                    distance_metric=BatchHardTripletLossDistanceFunction.cosine_distance,
                    margin=0.25,
                )

            train_steps = len(train_dataloader) * self.args.num_epochs
        else:
            train_examples = []

            for _ in range(self.num_epochs):
                train_examples = sentence_pairs_generation(np.array(x_train), np.array(y_train), train_examples)

            train_dataloader = DataLoader(train_examples, shuffle=True, batch_size=batch_size)
            train_loss = self.loss_class(self.model.model_body)
            train_steps = len(train_dataloader)

        print(f"{len(x_train)} train samples in total, {train_steps} train steps with batch size {batch_size}")

        warmup_steps = math.ceil(train_steps * 0.1)
        self.model.model_body.fit(
            train_objectives=[(train_dataloader, train_loss)],
            epochs=1,
            steps_per_epoch=train_steps,
            warmup_steps=warmup_steps,
            show_progress_bar=True,
        )

        # Train the final classifier
        self.model.fit(x_train, y_train)

    def evaluate(self):
        """Computes the metrics for a given classifier."""
        # Define metrics
        metric_fn = evaluate.load("accuracy")

        x_test = self.eval_dataset["text"]
        y_test = self.eval_dataset["label"]

        y_pred = self.model.predict(x_test)

        metrics = metric_fn.compute(predictions=y_pred, references=y_test)
        return metrics

    def predict(self):
        pass

    def push_to_hub(
        self,
        repo_path_or_name: Optional[str] = None,
        repo_url: Optional[str] = None,
        commit_message: Optional[str] = "Add model",
        organization: Optional[str] = None,
        private: Optional[bool] = None,
        api_endpoint: Optional[str] = None,
        use_auth_token: Union[bool, str] = None,
        git_user: Optional[str] = None,
        git_email: Optional[str] = None,
        config: Optional[dict] = None,
        skip_lfs_files: bool = False,
    ):

        return self.model.push_to_hub(
            repo_path_or_name,
            repo_url,
            commit_message,
            organization,
            private,
            api_endpoint,
            use_auth_token,
            git_user,
            git_email,
            config,
            skip_lfs_files,
        )
