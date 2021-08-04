import os
from typing import Tuple, List, Union

import pandas as pd
from spacy import Language
from spacy.tokens import Doc


def read_file(filename):
    with open(filename, 'r') as f:
        return f.read()


def read_brat_annotation(filename: str) -> pd.DataFrame:
    """
    Read BRAT annotation file and returns a pandas DataFrame.

    Parameters
    ----------
    filename:
        Path to the annotation file.

    Returns
    -------
    annotations:
        DataFrame containing the annotations.
    """

    try:
        annotations = pd.read_csv(filename, sep='\t', header=None)

        annotations.columns = ['index', 'annot', 'lexical_variant']

        annotations['end'] = annotations.annot.str.split().str[-1]
        annotations['annot'] = annotations.annot.str.split(';').str[0]

        annotations['label'] = annotations.annot.str.split().str[:-2].str.join(' ')
        annotations['start'] = annotations.annot.str.split().str[-2]

        annotations = annotations[['index', 'start', 'end', 'label', 'lexical_variant']]

    except pd.errors.EmptyDataError:
        annotations = pd.DataFrame(columns=['index', 'start', 'end', 'label', 'lexical_variant'])

    annotations[['start', 'end']] = annotations[['start', 'end']].astype(int)
    return annotations


class BratConnector(object):

    def __init__(self, directory: str):
        self.directory = directory

        os.makedirs(directory, exist_ok=True)

    def full_path(self, filename: str) -> str:
        return os.path.join(self.directory, filename)

    def read_file(self, filename: str) -> str:
        """
        Reads a file within the BRAT directory.

        Parameters
        ----------
        filename:
            The path to the file within the BRAT directory.

        Returns
        -------
        text:
            The text content of the file.
        """
        with open(self.full_path(filename), 'r', encoding='utf-8') as f:
            return f.read()

    def read_texts(self) -> pd.DataFrame:
        """
        Reads all texts from the BRAT folder.

        Returns
        -------
        texts:
            DataFrame containing all texts in the BRAT directory.
        """
        files = os.listdir(self.directory)
        filenames = [f[:-4] for f in files if f.endswith('.txt')]

        texts = pd.DataFrame(dict(note_id=filenames))

        texts['note_text'] = (texts.note_id + '.txt').apply(self.read_file)

        return texts

    def read_brat_annotation(self, note_id: Union[str, int]) -> pd.DataFrame:
        """
        Reads BRAT annotation inside the BRAT directory.

        Parameters
        ----------
        note_id:
            Note ID within the BRAT directory.

        Returns
        -------
        annotations:
            DataFrame containing the annotations for the given note.
        """
        filename = f"{note_id}.ann"
        annotations = read_brat_annotation(self.full_path(filename))
        return annotations

    def get_brat(self) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        Reads texts and annotations, and returns two DataFrame objects.

        Returns
        -------
        texts:
            A DataFrame containing two fields, `note_id` and `note_text`
        annotations:
            A DataFrame containing the annotations.
        """

        texts = self.read_texts()

        dfs = [
            self.read_brat_annotation(note_id)
            for note_id in texts.note_id
        ]

        annotations = pd.concat(
            dfs,
            keys=texts.note_id,
            names=['note_id']
        )

        annotations = annotations.droplevel(1).reset_index()

        return texts, annotations

    def brat2docs(self, nlp: Language) -> List[Doc]:
        """
        Transforms a BRAT folder to a list of Spacy documents.

        Parameters
        ----------
        nlp:
            A Spacy pipeline.

        Returns
        -------
        docs:
            List of Spacy documents, with annotations in the `ents` attribute.
        """
        texts, annotations = self.get_brat()

        docs = list(nlp.pipe(texts.note_text))

        for note_id, doc in zip(texts.note_id, docs):

            doc._.note_id = note_id

            ann = annotations.query('note_id == @note_id')

            spans = []

            for _, row in ann.iterrows():
                span = doc.char_span(
                    row.start,
                    row.end,
                    label=row.label,
                    alignment_mode='expand',
                )
                spans.append(span)

            doc.ents = spans

        return docs

    def doc2brat(self, doc: Doc) -> None:
        """
        Writes a Spacy document to file in the BRAT directory.

        Parameters
        ----------
        doc:
            Spacy Doc object. The spans in `ents` will populate the `note_id.ann` file.
        """
        filename = str(doc._.note_id)

        with open(self.full_path(f'{filename}.txt'), 'w', encoding='utf-8') as f:
            f.write(doc.text)

        annotations = pd.DataFrame.from_records([
            dict(
                label=ann.label_,
                lexical_variant=ann.text,
                start=ann.start_char,
                end=ann.end_char,
            )
            for ann in doc.ents
        ])

        if len(annotations) > 0:

            annotations['annot'] = annotations.label \
                                   + ' ' + annotations.start.astype(str) \
                                   + ' ' + annotations.end.astype(str)

            annotations['index'] = [f'T{i + 1}' for i in range(len(annotations))]

            annotations = annotations[['index', 'annot', 'lexical_variant']]
            annotations.to_csv(
                self.full_path(f'{filename}.ann'),
                sep='\t',
                header=None,
                index=False,
                encoding='utf-8',
            )

        else:
            open(self.full_path(f'{filename}.ann'), 'w', encoding='utf-8').close()

    def docs2brat(self, docs: List[Doc]) -> None:
        """
        Writes a list of Spacy documents to file.

        Parameters
        ----------
        docs:
            List of Spacy documents.
        """
        for doc in docs:
            self.doc2brat(doc)