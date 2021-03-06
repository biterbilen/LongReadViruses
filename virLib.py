import os
import sys
import subprocess
import time
import requests

# BioPython
from Bio import Entrez
from Bio.Blast import NCBIWWW # NCBI API wrapper
from Bio.Blast import NCBIXML # parse output BLAST XML
from Bio import SeqIO # ingests fastas


# SRR5383888
# Human w/ HBV (PacBio): https://www.ncbi.nlm.nih.gov/sra/SRX2678953[accn]

# SRR5383891
# Human w/ HBV (PacBio; Control): https://www.ncbi.nlm.nih.gov/sra/SRX2678956[accn]

# SRR6172653
# PacBio Soil Samples: https://www.ncbi.nlm.nih.gov/sra/SRX3283433[accn]

# SRR6172655
# PacBio Soil Samples: https://www.ncbi.nlm.nih.gov/sra/SRX3283431[accn]

class VirLib(object):
    def __init__(self):
        self.SRA_tool_path = self.installSRAtoolkit()
        self.fastq_dump_path = os.path.join(self.SRA_tool_path, 'fastq-dump')

    def installSRAtoolkit(self):
        """
        Compiled and tested on Ubuntu.

        :return:
        """
        tools_dir = os.getcwd()
        SRA_tar_path = os.path.join(tools_dir, 'sratoolkit.current-centos_linux64.tar.gz')
        SRA_tar_url = 'http://ftp-trace.ncbi.nlm.nih.gov/sra/sdk/current/sratoolkit.current-centos_linux64.tar.gz'
        # decompresses into version 2.9.0 for some reason
        SRA_tool_path = os.path.join(tools_dir, 'sratoolkit.2.9.0-centos_linux64/bin')
        # /home/lifeisaboutfishtacos/Desktop/virusRepo/LongReadViruses/sratoolkit.2.9.0-centos_linux64/bin

        # if there's no SRA_toolkit tar, fetch it from ftp
        if not os.path.exists(SRA_tar_path):
            ftp_fetch = ["wget", "-P", tools_dir, SRA_tar_url]
            subprocess.check_call(ftp_fetch)
        # extract the compressed SRA_toolkit if not already extracted
        if not os.path.exists(SRA_tool_path):
            decompress_SRA_tools = ['tar', '-xzf', SRA_tar_path]
            subprocess.check_call(decompress_SRA_tools)

        assert os.path.exists(SRA_tool_path)
        return SRA_tool_path

    def processInput(self, type, input):
        """
        Returns the filepath to a local fasta file.

        Fetches fasta by SRR code if necessary.

        :param type:
        :param input:
        :return:
        """
        if type == 'fasta':
            assert (input.endswith('.fasta') or
                    input.endswith('.fa') or
                    input.endswith('.fastq') or
                    input.endswith('.fq'))
            return os.path.abspath(input)
        if type == 'srr':
            return self.getSRR(SRR_code=input)

    def getSRR(self, SRR_code):
        """
        Takes an SRR code, downloads it as a fastq, and returns the path to that fastq file.

        API Documentation: https://trace.ncbi.nlm.nih.gov/Traces/sra/sra.cgi?view=toolkit_doc&f=fastq-dump

        :param SRR_code:
        :return: filepath of downloaded fasta
        """
        # basic example cmd: "./fastq-dump -X 5 -Z SRR5150787"
        sratools_API_cmd = "{fastq_dump_path} -Z {SRR_code} > {SRR_code}.fastq" \
                           "".format(fastq_dump_path=self.fastq_dump_path,
                                     SRR_code=SRR_code)
        # run the command
        print('Now running: {cmd}'.format(cmd=sratools_API_cmd))
        process = subprocess.Popen(sratools_API_cmd, shell=True)
        process.communicate()
        # assert the output file was created and return
        SRR_filepath = os.path.join(os.getcwd(), SRR_code + '.fastq')
        assert os.path.exists(SRR_filepath)

        # throttle requests so that we don't contact the server more than once every 10 seconds
        # More Info: https://blast.ncbi.nlm.nih.gov/Blast.cgi?CMD=Web&PAGE_TYPE=BlastDocs&DOC_TYPE=DeveloperInfo
        time.sleep(11)

        return os.path.join(SRR_filepath)

    def blastAPISearch(self, record, output_xml_path='default.xml'):
        """
        Takes a fasta/fastq, runs BLAST, saves the XML outputs, and returns the xml path..

        :param fastq_path:
        :param output_xml_path:
        :return:
        """
        # process fasta as a biopython sequence record object
        result_handle = NCBIWWW.qblast("blastn", "nt", record.seq)

        # save the output as an xml file
        with open(output_xml_path, "w") as out_handle:
            out_handle.write(result_handle.read())
        return os.path.abspath(output_xml_path)

    def fetchXMLResults(self, output_xml_path):
        """
        Looks for the words 'virus or 'viral' in the xml headers and returns those that match.  If
        none match, (slowly) fetch the GenBank accession files and determine the organism.

        :param output_xml_path:
        :return:
        """
        matches = []
        accessions = []
        with open(output_xml_path, "r") as out_handle:
            blast_records = NCBIXML.parse(out_handle)
            for blast_record in blast_records:
                for alignment in blast_record.alignments:
                    accessions.append(self.parseAccession(alignment.title))
                    # fetch the organism by the accession number instead
                    # possibly write if we care about the e value (hsp.expect)
                    if 'virus' in alignment.title or 'viral' in alignment.title:
                        matches.append(alignment.title)
        if matches:
            return matches
        else:
            return self.checkAccessions(accessions_list=accessions)

    def parseAccession(self, alignment_title):
        """"
        Given a SeqRecord, return the accession number as a string.

        Modified from biopython.org.

        e.g. "gi|2765613|emb|Z78488.1|PTZ78488" -> "Z78488.1"
        """
        parts = alignment_title.split("|")
        print(parts)
        assert parts[0] == "gi"
        return parts[3]

    def organismNamefromGenBankAccession(self, accessionCode):
        """
        Returns an organism's English name from a GenBank accession number.

        :param accessionCode:
        :return: String
        """

        # throttle requests so that we don't contact the server more than once every 10 seconds
        # More Info: https://blast.ncbi.nlm.nih.gov/Blast.cgi?CMD=Web&PAGE_TYPE=BlastDocs&DOC_TYPE=DeveloperInfo
        time.sleep(11)

        Entrez.email = 'lblauvel@ucsc.edu'
        records_handle = Entrez.efetch(db="nuccore", rettype="gb", id=accessionCode)
        for record in records_handle:
            record = record.strip()
            if record.startswith('ORGANISM'):
                return record # [len('ORGANISM'):].strip()

    def checkAccessions(self, accessions_list):
        resulting_organisms = []
        for accession in accessions_list:
            resulting_organisms.append(self.organismNamefromGenBankAccession(accession))
        return resulting_organisms

    def printXMLresults(self, output_xml_path):
        """
        Only for debugging/verifying output.

        :param result_handle:
        :return:
        """
        # read the xml
        with open(output_xml_path, "r") as out_handle:
            blast_records = NCBIXML.parse(out_handle)
            for blast_record in blast_records:
                for alignment in blast_record.alignments:
                    for hsp in alignment.hsps:
                        print('****Alignment****')
                        print('sequence:', alignment.title)
                        print('length:', alignment.length)
                        print('e value:', hsp.expect)
                        print(hsp.query[0:75] + '...')
                        print(hsp.match[0:75] + '...')
                        print(hsp.sbjct[0:75] + '...')

    def entriesFromFastq(self, fastq):
        """
        fastq files may have multiple entries.  This returns a list of BioPython record objects
        associated with each fastq entry.

        :param fastq:
        :return:
        """
        from Bio import SeqIO
        entries = []
        with open(fastq, "rU") as handle:
            for record in SeqIO.parse(handle, "fastq"):
                entries.append(record)
        return entries


# # TESTING inputs with SRR fetching
# v = VirLib()
# rv1 = v.process_input(type='fasta', input='input.fa')
# print(rv1)
# rv2 = v.process_input(type='srr', input='SRR5150787')
# print(rv2)

# # TESTING biopython BLAST API
# v = VirLib()
# rv2 = v.process_inputs(type='srr', input='SRR5383888')
# print(rv2)
# v.blast_API_search(rv2, output_xml_path= 'default.xml')

# v = VirLib()
# x = ['SRR6172655', 'SRR6172653', 'SRR5383891', 'SRR5383888']
# for i in x:
#     v.process_inputs(type='srr', input=i)

# v = VirLib()
# v.organismNamefromGenBankAccession('KY881787.1')

v = VirLib()
fastq_path = v.processInput(type='srr', input='SRR5383888')
entries = v.entriesFromFastq(fastq=fastq_path)
for record in entries:
    output_xml_path = v.blastAPISearch(record, output_xml_path='default.xml')
    species_list = v.fetchXMLResults(output_xml_path)
    for i in species_list:
        print(i)
